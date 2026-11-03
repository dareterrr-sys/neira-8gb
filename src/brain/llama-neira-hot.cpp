#include "llama-neira-hot.h"

#include "llama-impl.h"
#include "llama-model.h"

#include <algorithm>
#include <map>
#include <mutex>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>

static bool neira_hot_host_weight(const ggml_tensor * t) {
    return t != nullptr && t->buffer != nullptr &&
        ggml_backend_buffer_get_usage(t->buffer) == GGML_BACKEND_BUFFER_USAGE_WEIGHTS &&
        ggml_backend_buffer_is_host(t->buffer);
}

llama_neira_hot::llama_neira_hot(const llama_model & model, const std::vector<ggml_backend_t> & backends,
                                 const std::vector<ggml_backend_buffer_type_t> & bufts, const std::string & path) {
    // the pool: per layer k hot experts by use, then one stand-in for the cold side (the next most used expert)
    FILE * f = fopen(path.c_str(), "rb");
    if (f == nullptr) {
        throw std::runtime_error("NEIRA_HOT_EXPERTS: cannot open " + path);
    }
    int32_t n_layer_f = 0;
    int32_t k = 0;
    bool ok = fread(&n_layer_f, sizeof(int32_t), 1, f) == 1 && fread(&k, sizeof(int32_t), 1, f) == 1 &&
        n_layer_f > 0 && k > 0;
    std::vector<int32_t> pool(ok ? (size_t) n_layer_f*(k + 1) : 0);
    ok = ok && fread(pool.data(), sizeof(int32_t), pool.size(), f) == pool.size();
    fclose(f);
    if (!ok) {
        throw std::runtime_error("NEIRA_HOT_EXPERTS: bad file " + path);
    }

    ggml_backend_t gpu = nullptr;
    ggml_backend_buffer_type_t gpu_buft = nullptr;
    for (size_t i = 0; i < backends.size(); ++i) {
        if (ggml_backend_dev_type(ggml_backend_get_device(backends[i])) == GGML_BACKEND_DEVICE_TYPE_GPU) {
            gpu      = backends[i];
            gpu_buft = bufts[i];
            break;
        }
    }
    if (gpu == nullptr) {
        throw std::runtime_error("NEIRA_HOT_EXPERTS needs a GPU");
    }
    const int64_t n_expert = model.hparams.n_expert;
    const size_t  n_layer  = std::min((size_t) n_layer_f, model.layers.size());
    layers.resize(model.layers.size());

    // the pool shrinks to the free VRAM: the compute buffers (made after this) and the author's other programs
    // (games, browsers: 1-2.5 GiB that comes and goes) must still fit, or the driver spills VRAM into RAM and
    // generation falls from ~42 to ~5 tokens/s (28.10)
    int32_t k_use = k;
    {
        size_t free = 0;
        size_t total = 0;
        ggml_backend_dev_memory(ggml_backend_get_device(gpu), &free, &total);
        // on Windows (WDDM) CUDA's free memory ignores the other programs (a game's 2 GiB, 28.10): the launcher passes
        // nvidia-smi's free memory measured before the brain started, and what this process took since is subtracted
        if (const char * f = getenv("NEIRA_HOT_FREE_MIB"); f != nullptr && atoll(f) > 0) {
            const size_t before = (size_t) atoll(f)*1024*1024;
            const size_t ours   = total > free ? total - free : 0;
            const size_t left   = before > ours ? before - ours : 0;
            LLAMA_LOG_INFO("%s: CUDA says %.0f MiB free, nvidia-smi before start %.0f MiB - ours %.0f MiB = %.0f MiB\n",
                __func__, free/1048576.0, before/1048576.0, ours/1048576.0, left/1048576.0);
            free = std::min(free, left);
        }
        const char * r = getenv("NEIRA_HOT_RESERVE_MIB");
        // 2600: ~1 GiB of compute buffers made after the pool (-ub 2048 + the MTP context) + ~1.5 GiB for the
        // programs that grow later; 1600 was too little with a game open (0.5 tokens/s, 28.10)
        const size_t reserve = (size_t) (r ? atoll(r) : 2600)*1024*1024;
        size_t per_k = 0; // one more hot expert in every layer
        for (size_t il = 0; il < n_layer; ++il) {
            const llama_layer & L = model.layers[il];
            if (L.ffn_up_exps && L.ffn_gate_exps && L.ffn_down_exps) {
                per_k += L.ffn_up_exps->nb[2] + L.ffn_gate_exps->nb[2] + L.ffn_down_exps->nb[2];
            }
        }
        const size_t fit = free > reserve && per_k > 0 ? (free - reserve)/per_k : 0;
        k_use = (int32_t) std::min<size_t>((size_t) k, fit > 2 ? fit - 2 : 0); // 2 slots: the zero expert, the MMQ pad
        LLAMA_LOG_INFO("%s: free VRAM %.0f MiB, reserve %.0f MiB -> %d of %d hot experts per layer\n", __func__,
            free/1048576.0, reserve/1048576.0, k_use, k);
        if (k_use < 4) {
            LLAMA_LOG_WARN("%s: not enough free VRAM, hot experts are off\n", __func__);
            layers.clear();
            return;
        }
    }

    auto init_ctx = [](size_t n_tensors) {
        ggml_init_params params = {
            /*.mem_size   =*/ n_tensors*ggml_tensor_overhead(),
            /*.mem_buffer =*/ nullptr,
            /*.no_alloc   =*/ true,
        };
        ggml_context_ptr res(ggml_init(params));
        if (!res) {
            throw std::runtime_error("NEIRA_HOT_EXPERTS: context");
        }
        return res;
    };
    ctx_dev  = init_ctx(n_layer*8);
    ctx_host = init_ctx(n_layer);

    std::vector<std::vector<int32_t>> hot(n_layer);
    std::vector<int32_t> stand_in(n_layer, -1);
    size_t n_hot = 0;
    for (size_t il = 0; il < n_layer; ++il) {
        const llama_layer & L = model.layers[il];
        if (L.ffn_gate_up_exps != nullptr || !neira_hot_host_weight(L.ffn_up_exps) ||
            !neira_hot_host_weight(L.ffn_gate_exps) || !neira_hot_host_weight(L.ffn_down_exps)) {
            continue;
        }
        std::vector<bool> seen(n_expert, false);
        for (int32_t j = 0; j < k_use; ++j) {
            const int32_t e = pool[il*(k + 1) + j];
            if (e >= 0 && e < n_expert && !seen[e]) {
                seen[e] = true;
                hot[il].push_back(e);
            }
        }
        const int32_t s = pool[il*(k + 1) + k];
        stand_in[il] = s >= 0 && s < n_expert && !seen[s] ? s : -1;
        for (int32_t e = 0; stand_in[il] < 0 && e < n_expert; ++e) {
            if (!seen[e]) {
                stand_in[il] = e;
            }
        }
        if (hot[il].empty() || stand_in[il] < 0) {
            hot[il].clear();
            continue;
        }

        layer & l = layers[il];
        const int64_t n_slots = (int64_t) hot[il].size();
        // one zero expert at slot n_slots for the cold experts, one more slot because CUDA MMQ can read past the last
        auto bank = [&](const ggml_tensor * w, const char * name) {
            ggml_tensor * b = ggml_new_tensor_3d(ctx_dev.get(), w->type, w->ne[0], w->ne[1], n_slots + 2);
            GGML_ASSERT(b->nb[2] == w->nb[2]);
            ggml_format_name(b, "neira_hot.%zu.%s", il, name);
            ggml_tensor * v = ggml_view_3d(ctx_dev.get(), b, b->ne[0], b->ne[1], n_slots + 1, b->nb[1], b->nb[2], 0);
            ggml_format_name(v, "neira_hot.%zu.%s.v", il, name);
            return v;
        };
        l.up   = bank(L.ffn_up_exps,   "up");
        l.gate = bank(L.ffn_gate_exps, "gate");
        l.down = bank(L.ffn_down_exps, "down");
        l.hot_map = ggml_new_tensor_2d(ctx_dev.get(), GGML_TYPE_I32, 1, n_expert);
        l.cold_w  = ggml_new_tensor_2d(ctx_dev.get(), GGML_TYPE_F32, 1, n_expert);
        l.cold_map = ggml_new_tensor_2d(ctx_host.get(), GGML_TYPE_I32, 1, n_expert);
        ggml_format_name(l.hot_map,  "neira_hot.hot_map-%zu",  il);
        ggml_format_name(l.cold_w,   "neira_hot.cold_w-%zu",   il);
        ggml_format_name(l.cold_map, "neira_hot.cold_map-%zu", il);
        l.on = true;
        n_hot += hot[il].size();
    }
    if (n_hot == 0) {
        LLAMA_LOG_WARN("%s: no layer with host experts, hot experts are off\n", __func__);
        layers.clear();
        return;
    }

    buf_dev.reset(ggml_backend_alloc_ctx_tensors_from_buft(ctx_dev.get(), gpu_buft));
    buf_host.reset(ggml_backend_alloc_ctx_tensors_from_buft(ctx_host.get(), ggml_backend_cpu_buffer_type()));
    if (!buf_dev || !buf_host) {
        throw std::runtime_error("NEIRA_HOT_EXPERTS: cannot allocate the banks");
    }
    ggml_backend_buffer_clear(buf_dev.get(), 0); // the zero expert
    // as weights: the ops that read the banks run on the GPU, the cold map lookup on the CPU
    ggml_backend_buffer_set_usage(buf_dev.get(),  GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
    ggml_backend_buffer_set_usage(buf_host.get(), GGML_BACKEND_BUFFER_USAGE_WEIGHTS);

    for (size_t il = 0; il < n_layer; ++il) {
        layer & l = layers[il];
        if (!l.on) {
            continue;
        }
        const int32_t n_slots = (int32_t) hot[il].size();
        std::vector<int32_t> hot_map(n_expert, n_slots);
        std::vector<int32_t> cold_map(n_expert);
        std::vector<float>   cold_w(n_expert, 1.0f);
        for (int64_t e = 0; e < n_expert; ++e) {
            cold_map[e] = (int32_t) e;
        }
        for (int32_t j = 0; j < n_slots; ++j) {
            const int32_t e = hot[il][j];
            hot_map[e]  = j;
            cold_map[e] = -1; // skipped by the CPU mul_mat_id (its row is zero there)
            cold_w[e]   = 0.0f;
        }
        ggml_backend_tensor_set(l.hot_map, hot_map.data(), 0, ggml_nbytes(l.hot_map));
        ggml_backend_tensor_set(l.cold_w,  cold_w.data(),  0, ggml_nbytes(l.cold_w));
        ggml_backend_tensor_set(l.cold_map, cold_map.data(), 0, ggml_nbytes(l.cold_map));
    }
    // the expert weights are copied at the first decode (fill): when the context is made, the host experts may not
    // have their data yet (data == NULL here, 28.10)
    mdl = &model;
    hot_ids = std::move(hot);

    LLAMA_LOG_INFO("%s: %zu hot experts in %zu layers, %.2f MiB of VRAM (%s)\n", __func__, n_hot, n_layer,
        ggml_backend_buffer_get_size(buf_dev.get())/1024.0/1024.0, path.c_str());
}

std::shared_ptr<llama_neira_hot> llama_neira_hot::shared(const llama_model & model, const std::vector<ggml_backend_t> & backends,
                                                         const std::vector<ggml_backend_buffer_type_t> & bufts, const std::string & path) {
    static std::mutex mtx;
    static std::map<const llama_model *, std::weak_ptr<llama_neira_hot>> pools;
    std::lock_guard<std::mutex> lock(mtx);
    if (auto p = pools[&model].lock()) {
        return p;
    }
    auto p = std::make_shared<llama_neira_hot>(model, backends, bufts, path);
    pools[&model] = p;
    return p;
}

void llama_neira_hot::fill() {
    if (filled || mdl == nullptr) {
        return;
    }
    std::vector<uint8_t> tmp;
    size_t n = 0;
    for (size_t il = 0; il < hot_ids.size(); ++il) {
        const layer & l = layers[il];
        if (!l.on) {
            continue;
        }
        const llama_layer & L = mdl->layers[il];
        for (size_t j = 0; j < hot_ids[il].size(); ++j) {
            const size_t e = (size_t) hot_ids[il][j];
            for (auto [w, b] : { std::pair{ L.ffn_up_exps, l.up }, { L.ffn_gate_exps, l.gate }, { L.ffn_down_exps, l.down } }) {
                const size_t sz = w->nb[2];
                if (w->data != nullptr) {
                    ggml_backend_tensor_set(b, (const uint8_t *) w->data + e*sz, j*sz, sz);
                } else {
                    tmp.resize(sz);
                    ggml_backend_tensor_get(w, tmp.data(), e*sz, sz);
                    ggml_backend_tensor_set(b, tmp.data(), j*sz, sz);
                }
            }
            n++;
        }
    }
    filled = true;
    LLAMA_LOG_INFO("%s: %zu hot experts copied to VRAM\n", __func__, n);
}
