#pragma once

// Neira hot experts (28.10): the mixed CPU/GPU split of the MoE layers.
// The experts stay in host memory; the most used ones (by the expert map) are also copied once into VRAM banks.
// In generation the selected experts are split: the hot ones are computed on the GPU from the banks, the cold ones
// on the CPU from host memory, and the two halves are added. Nothing is uploaded per token (unlike the MoE cache).
// Enabled by NEIRA_HOT_EXPERTS=<file>: int32 n_layer, int32 k, then n_layer*k int32 expert ids (-1 = none).

#include "ggml-backend.h"
#include "ggml-cpp.h"

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

struct llama_model;

class llama_neira_hot {
public:
    struct layer {
        bool on = false;
        ggml_tensor * up   = nullptr; // VRAM banks, k hot experts + 1 zero expert (slot k)
        ggml_tensor * gate = nullptr;
        ggml_tensor * down = nullptr;
        ggml_tensor * hot_map  = nullptr; // I32 [1, n_expert] VRAM: expert -> its slot, or k (the zero expert)
        ggml_tensor * cold_map = nullptr; // I32 [1, n_expert] host: expert -> itself, or a stand-in cold expert
        ggml_tensor * cold_w   = nullptr; // F32 [1, n_expert] VRAM: 1 for cold experts, 0 for hot
    };

    llama_neira_hot(const llama_model & model, const std::vector<ggml_backend_t> & backends,
                    const std::vector<ggml_backend_buffer_type_t> & bufts, const std::string & path);

    // one pool per model: the MTP draft context makes its own llama_context, and two copies of the banks would
    // take the VRAM twice (28.10: +1.4 GiB for a 0.6 GiB pool)
    static std::shared_ptr<llama_neira_hot> shared(const llama_model & model, const std::vector<ggml_backend_t> & backends,
                                                   const std::vector<ggml_backend_buffer_type_t> & bufts, const std::string & path);

    const layer * get(int32_t il) const {
        return il >= 0 && il < (int32_t) layers.size() && layers[il].on ? &layers[il] : nullptr;
    }

    // copy the hot experts into the banks once, at the first decode (the host experts have their data by then)
    void fill();

    // generation only: large batches use most experts and are better served by the usual path (op offload)
    // up to 8: CUDA takes the mmvq path for mul_mat_id; 9-16 token batches (MMQ) crashed with an illegal memory access
    // on the banks (28.10, a prompt continued from the cache); they are rare and go the usual way
    static constexpr int64_t max_tokens = 8;

private:
    std::vector<layer> layers;
    const llama_model * mdl = nullptr;
    std::vector<std::vector<int32_t>> hot_ids;
    bool filled = false;
    ggml_context_ptr ctx_dev;
    ggml_context_ptr ctx_host;
    ggml_backend_buffer_ptr buf_dev;
    ggml_backend_buffer_ptr buf_host;
};
