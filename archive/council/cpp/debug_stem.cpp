// Отладка stem(): точная копия логики из units.cpp с печатью шагов.
#include <cstdio>
#include <cctype>
#include <map>
#include <string>
#include <vector>

static std::string utf8_tolower(const std::string& s) {
    std::string r = s;
    for (size_t i = 0; i < r.size(); ++i) {
        unsigned char c = (unsigned char)r[i];
        if (c == 0xD0 && i + 1 < r.size()) {
            unsigned char c2 = (unsigned char)r[i + 1];
            if (c2 >= 0x90 && c2 <= 0xAF) {
                r[i + 1] = (char)(c2 + 0x20);
                ++i;
            }
        }
    }
    return r;
}

static std::string utf8_yo_to_e(const std::string& s) {
    std::string r;
    r.reserve(s.size());
    for (size_t i = 0; i < s.size(); ++i) {
        unsigned char c = (unsigned char)s[i];
        if (c == 0xD0 && i + 1 < s.size()) {
            unsigned char c2 = (unsigned char)s[i + 1];
            if (c2 == 0x91) { r += "\xD0\xB5"; ++i; continue; }
            if (c2 == 0xB1) { r += "\xD0\xB5"; ++i; continue; }
        }
        r += (char)c;
    }
    return r;
}

static std::string strip_ws(const std::string& s) {
    size_t a = 0, b = s.size();
    while (a < b && std::isspace((unsigned char)s[a])) ++a;
    while (b > a && std::isspace((unsigned char)s[b - 1])) --b;
    return s.substr(a, b - a);
}

static bool has_suffix(const std::string& s, const std::string& suf) {
    return s.size() >= suf.size() && s.compare(s.size() - suf.size(), suf.size(), suf) == 0;
}

static const std::vector<std::string>& ENDINGS() {
    static const std::vector<std::string> v = {
        "ами", "ями", "ов", "ев", "ей", "ах", "ях", "ам", "ям",
        "ой", "ий", "ия", "ие", "ья", "ье", "а", "я", "ы", "и",
        "у", "ю", "е", "о", "ь", "й",
    };
    return v;
}

static void dump(const char* label, const std::string& s) {
    printf("%s: ", label);
    for (unsigned char c : s) printf("%02x ", c);
    printf(" | as text: ");
    for (unsigned char c : s) printf("%c", c);
    printf("\n");
}

int main() {
    std::string w0 = "рублей";
    std::string w = utf8_yo_to_e(utf8_tolower(w0));
    dump("w after norm", w);
    // strip " ."
    size_t a = 0, b = w.size();
    while (a < b && (w[a] == ' ' || w[a] == '.')) ++a;
    while (b > a && (w[b-1] == ' ' || w[b-1] == '.')) --b;
    w = w.substr(a, b - a);
    dump("w stripped", w);
    std::string s = w;
    int found = -1;
    for (size_t idx = 0; idx < ENDINGS().size(); ++idx) {
        const auto& end = ENDINGS()[idx];
        bool m = has_suffix(w, end);
        if (m) {
            printf("first match ending[%zu] = '", idx);
            for (unsigned char c : end) printf("%c", c);
            printf("' (bytes ");
            for (unsigned char c : end) printf("%02x ", c);
            printf(")\n");
            s = w.substr(0, w.size() - end.size());
            found = (int)idx;
            break;
        }
    }
    dump("s after cut", s);
    printf("found idx=%d\n", found);
    return 0;
}
