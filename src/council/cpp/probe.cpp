// probe.cpp — датчик сомнения Нейры (линейная модель 2048 весов) на C++.
// Формула (как в patch_probe_server.py):  z = b + sum(w[i]*h[i]);
//                                        p = 1/(1+exp(-z)).
// Данные: probe16.json вида {"layer":16,"w":[...],"b":...}.
// Сборка: g++ -std=c++17 -O2 -shared -o probe.dll probe.cpp
// C-интерфейс для вызова из Python через ctypes.

#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

// ---- Мини-парсер JSON для нашего конкретного формата ----
// probe16.json содержит ровно: {"layer": N, "w": [числа], "b": число}.
// Парсер не универсальный, но tolerant: ищет ключи и собирает числа.

struct Probe {
    int layer = 0;
    std::vector<double> w;
    double b = 0.0;
};

static bool parse_probe(const std::string& text, Probe& out) {
    // ищем "layer": <int>
    auto find_key = [&](const char* key) -> size_t {
        return text.find(key);
    };
    size_t p = find_key("\"layer\"");
    if (p == std::string::npos) return false;
    p = text.find(':', p);
    if (p == std::string::npos) return false;
    out.layer = std::atoi(text.c_str() + p + 1);

    // ищем "w": [ ... ] и достаём все числа из скобок
    p = find_key("\"w\"");
    if (p == std::string::npos) return false;
    p = text.find('[', p);
    if (p == std::string::npos) return false;
    size_t end = text.find(']', p);
    if (end == std::string::npos) return false;
    std::string body = text.substr(p + 1, end - p - 1);
    {
        // числа разделены запятыми и пробелами
        std::string cur;
        for (char c : body) {
            if (c == ',' || c == ' ' || c == '\n' || c == '\t' || c == '\r') {
                if (!cur.empty()) {
                    out.w.push_back(std::atof(cur.c_str()));
                    cur.clear();
                }
            } else {
                cur += c;
            }
        }
        if (!cur.empty()) out.w.push_back(std::atof(cur.c_str()));
    }

    // ищем "b": <число>
    p = find_key("\"b\"");
    if (p == std::string::npos) return false;
    p = text.find(':', p);
    if (p == std::string::npos) return false;
    out.b = std::atof(text.c_str() + p + 1);
    return true;
}

static double sigmoid(double z) {
    return 1.0 / (1.0 + std::exp(-z));
}

static double probe_score(const Probe& pr, const double* h, int n) {
    double z = pr.b;
    int m = (int)pr.w.size();
    if (n > m) n = m;
    for (int i = 0; i < n; ++i) z += pr.w[i] * h[i];
    return sigmoid(z);
}

// ---- C-interop ----
extern "C" {

// Глобальная загруженная модель (для простоты — одна)
static Probe g_probe;

// Вотprobe_load(path) -> 1 при успехе
int probe_load(const char* path) {
    std::ifstream f(path);
    if (!f.is_open()) return 0;
    std::stringstream ss;
    ss << f.rdbuf();
    Probe p;
    if (!parse_probe(ss.str(), p)) return 0;
    g_probe = p;
    return 1;
}

// probe_score_for(h, n) -> p (если модель не загружена -> -1)
double probe_score_for(const double* h, int n) {
    if (g_probe.w.empty()) return -1.0;
    return probe_score(g_probe, h, n);
}

// probe_layer() -> номер слоя (0 если не загружена)
int probe_layer() {
    return g_probe.layer;
}

// probe_weights_count() -> число весов
int probe_weights_count() {
    return (int)g_probe.w.size();
}

// probe_weights(i) -> i-й вес
double probe_weights(int i) {
    if (i < 0 || i >= (int)g_probe.w.size()) return 0.0;
    return g_probe.w[i];
}

// probe_bias() -> b
double probe_bias() {
    return g_probe.b;
}

} // extern "C"
