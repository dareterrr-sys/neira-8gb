"""Council v3.9: the doubt sensor inside llama-server. NEIRA_PROBE=<probe.json> ({"layer": 16, "w": [2048 floats],
"b": float}; the standardization folded in, see export_probe.py) loads a linear probe. A /completion request with
"probe": true reads the residual stream of that layer at the last evaluated token (send the neutral-format prompt with
n_predict 1, so the last evaluation is the prompt's last token) and returns "neira_probe": P(the brain knows) =
sigmoid(w.h + b). The read needs the scheduler's eval callback; it is installed only when NEIRA_PROBE is set.
Usage: python patch_probe_server.py   (patches llama.cpp-src/tools/server in place, idempotent)
"""
import pathlib

SRV = pathlib.Path(r"D:\AI\expert-map\llama.cpp-src\tools\server")


def patch(name, old, new):
    p = SRV / name
    s = p.read_text(encoding="utf-8")
    if new in s:
        print(name, "already patched")
        return
    assert s.count(old) == 1, (name, old[:60], s.count(old))
    p.write_text(s.replace(old, new), encoding="utf-8")
    print(name, "patched")


patch("server-task.h",
      "    float cvec = 0.0f; // neira: factor for the startup control vector in this request (0 = off)\n",
      "    float cvec = 0.0f; // neira: factor for the startup control vector in this request (0 = off)\n"
      "    bool probe = false; // neira: read the doubt sensor (NEIRA_PROBE) on this request\n")

patch("server-task.h",
      "    bool post_sampling_probs;\n    std::vector<completion_token_output> probs_output;\n"
      "    std::vector<std::string>  response_fields;\n\n    task_params generation_params;\n",
      "    bool post_sampling_probs;\n    std::vector<completion_token_output> probs_output;\n"
      "    std::vector<std::string>  response_fields;\n\n    task_params generation_params;\n\n"
      "    float neira_probe = -1.0f; // neira: the doubt sensor's P(knows), -1 = not asked\n")

patch("server-task.cpp",
      "    if (!stream && !probs_output.empty()) {\n"
      "        res[\"completion_probabilities\"] = completion_token_output::probs_vector_to_json(probs_output, post_sampling_probs);\n"
      "    }\n    return response_fields.empty() ? res : json_get_nested_values(response_fields, res);\n",
      "    if (!stream && !probs_output.empty()) {\n"
      "        res[\"completion_probabilities\"] = completion_token_output::probs_vector_to_json(probs_output, post_sampling_probs);\n"
      "    }\n"
      "    if (neira_probe >= 0.0f) {\n"
      "        res[\"neira_probe\"] = neira_probe;\n"
      "    }\n    return response_fields.empty() ? res : json_get_nested_values(response_fields, res);\n")

patch("server-schema.cpp",
      "    add((new field_json(\"cvec\"))\n",
      "    add((new field_json(\"probe\"))\n"
      "        ->set_desc(\"neira: return the doubt sensor's reading (needs NEIRA_PROBE at start)\")\n"
      "        ->set_handler([&](field_eval_context & ctx, const json & data) {\n"
      "            ctx.params.probe = data.at(\"probe\").get<bool>();\n"
      "        }));\n\n"
      "    add((new field_json(\"cvec\"))\n")

patch("server-context.cpp",
      "    common_control_vector_data cvec_data = { -1, {} };\n    float cvec_cur = 0.0f;\n",
      "    common_control_vector_data cvec_data = { -1, {} };\n    float cvec_cur = 0.0f;\n\n"
      "    // neira: the doubt sensor - a linear probe on one layer's residual stream at the last evaluated token\n"
      "    std::vector<float> probe_w;\n"
      "    float probe_b = 0.0f;\n"
      "    std::string probe_name;\n"
      "    bool probe_active = false;\n"
      "    float probe_score = -1.0f;\n\n"
      "    static bool probe_cb(struct ggml_tensor * t, bool ask, void * user_data) {\n"
      "        auto * self = (server_context_impl *) user_data;\n"
      "        if (ask) {\n"
      "            return self->probe_active && t->type == GGML_TYPE_F32 && self->probe_name == t->name;\n"
      "        }\n"
      "        const int64_t n_embd = t->ne[0];\n"
      "        if (n_embd != (int64_t) self->probe_w.size() || t->ne[1] < 1) {\n"
      "            return true;\n"
      "        }\n"
      "        std::vector<float> h(n_embd);\n"
      "        ggml_backend_tensor_get(t, h.data(), (t->ne[1] - 1) * t->nb[1], n_embd * sizeof(float));\n"
      "        double z = self->probe_b;\n"
      "        for (int64_t i = 0; i < n_embd; ++i) {\n"
      "            z += (double) self->probe_w[i] * h[i];\n"
      "        }\n"
      "        self->probe_score = (float) (1.0 / (1.0 + std::exp(-z)));\n"
      "        return true;\n"
      "    }\n")

patch("server-context.cpp",
      "        llama_init = common_init_from_params(params_base);\n",
      "        if (const char * probe_path = getenv(\"NEIRA_PROBE\")) {\n"
      "            std::ifstream f(probe_path);\n"
      "            std::stringstream text;\n"
      "            text << f.rdbuf();\n"
      "            const json probe = json::parse(text.str());\n"
      "            probe_w    = probe.at(\"w\").get<std::vector<float>>();\n"
      "            probe_b    = probe.at(\"b\").get<float>();\n"
      "            probe_name = \"l_out-\" + std::to_string(probe.at(\"layer\").get<int>());\n"
      "            params_base.cb_eval           = probe_cb;\n"
      "            params_base.cb_eval_user_data = this;\n"
      "            SRV_INF(\"neira: doubt sensor loaded from %s (%s, %zu weights)\\n\", probe_path, probe_name.c_str(), probe_w.size());\n"
      "        }\n\n"
      "        llama_init = common_init_from_params(params_base);\n")

patch("server-context.cpp",
      "        // neira: normally switched in get_available_slot already; this covers the paths that skip it\n",
      "        // neira: the doubt sensor reads this request's evaluations\n"
      "        probe_active = !probe_w.empty() && task.params.probe;\n"
      "        probe_score  = -1.0f;\n\n"
      "        // neira: normally switched in get_available_slot already; this covers the paths that skip it\n")

patch("server-context.cpp",
      "        res->n_tokens_cached       = slot.prompt.n_tokens();\n        res->has_new_line          = slot.has_new_line;\n",
      "        res->n_tokens_cached       = slot.prompt.n_tokens();\n        res->has_new_line          = slot.has_new_line;\n"
      "        if (slot.task->params.probe) {\n"
      "            res->neira_probe = probe_score;\n"
      "            probe_active     = false;\n"
      "        }\n")
