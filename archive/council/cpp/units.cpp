// units.cpp — C++ реализация units.py (проверка единиц для судьи по шагам).
// Перенос один в один: stem, unit, bracket, split, show.
// Сборка: clang++ -std=c++17 -O2 -shared -o units.dll units.cpp
// (или g++ -std=c++17 -O2 -shared -fPIC -o units.so units.cpp)
// Интерфейс наружу: C-функции, чтобы вызывать из Python через ctypes.

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

// ---- Вспомогательное: строки UTF-8 без фреймворков ------------------------
// Работаем с UTF-8 как с байтовыми строками (как Python с str).
// Нормализация ё -> е и lowercase кириллицы.

static std::string utf8_tolower(const std::string& s) {
    std::string r = s;
    for (size_t i = 0; i < r.size(); ++i) {
        unsigned char c = (unsigned char)r[i];
        if (c == 0xD0 && i + 1 < r.size()) {
            unsigned char c2 = (unsigned char)r[i + 1];
            if (c2 >= 0x90 && c2 <= 0xAF) { // А-Я -> а-я
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
            if (c2 == 0x81) { r += "\xD0\xB5"; ++i; continue; } // Ё (D0 81) -> е
        }
        if (c == 0xD1 && i + 1 < s.size()) {
            unsigned char c2 = (unsigned char)s[i + 1];
            if (c2 == 0x91) { r += "\xD0\xB5"; ++i; continue; } // ё (D1 91) -> е
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

// ---- Словарь сокращений (как _ABBR в units.py) ----------------------------
static const std::map<std::string, std::string>& ABBR() {
    static const std::map<std::string, std::string> m = {
        {"ч", "час"}, {"мин", "минут"}, {"с", "секунд"}, {"сек", "секунд"},
        {"руб", "рубл"}, {"р", "рубл"}, {"долл", "доллар"}, {"шт", "штук"},
        {"кг", "кг"}, {"г", "грамм"}, {"км", "км"}, {"м", "метр"},
        {"см", "см"}, {"мм", "мм"}, {"л", "литр"}, {"мл", "мл"},
        {"$", "доллар"}, {"₽", "рубл"}, {"%", "процент"}, {"фут", "фут"},
        {"ярд", "ярд"},
    };
    return m;
}

// Окончания для стеммера (как _END в units.py)
static const std::vector<std::string>& ENDINGS() {
    static const std::vector<std::string> v = {
        "ами", "ями", "ов", "ев", "ей", "ах", "ях", "ам", "ям",
        "ой", "ий", "ия", "ие", "ья", "ье", "а", "я", "ы", "и",
        "у", "ю", "е", "о", "ь", "й",
    };
    return v;
}

// stem(word): «часов» -> час, «занятия» -> занят, «мин» -> минут
static std::string stem(const std::string& word_in) {
    std::string w = utf8_yo_to_e(utf8_tolower(word_in));
    // strip " ." с концов
    size_t a = 0, b = w.size();
    while (a < b && (w[a] == ' ' || w[a] == '.')) ++a;
    while (b > a && (w[b-1] == ' ' || w[b-1] == '.')) --b;
    w = w.substr(a, b - a);
    auto it = ABBR().find(w);
    if (it != ABBR().end()) return it->second;
    std::string s = w;
    for (const auto& end : ENDINGS()) {
        if (has_suffix(w, end)) {
            s = w.substr(0, w.size() - end.size());
            break;
        }
    }
    if (s.size() >= 2) {
        auto it2 = ABBR().find(s);
        if (it2 != ABBR().end()) return it2->second;
    }
    return s;
}

// Единица как строка «U_имя^степень» (моном), 1 если нет единицы.
// В Python единицы — sympy-символы; здесь представляем как произведение строк
// вида "U_час^1 U_ден^-1" с нормализованным порядком.
static std::string unit_monomial(const std::string& text_in) {
    std::string text = strip_ws(text_in);
    if (!text.empty() && text.front() == '[' && text.back() == ']')
        text = text.substr(1, text.size() - 2);
    text = strip_ws(text);
    if (text == "" || text == "1" || text == "-" || text == "—")
        return "1";
    // разбить по "/"
    std::vector<std::string> parts;
    {
        std::string cur;
        for (char c : text) {
            if (c == '/') { parts.push_back(cur); cur.clear(); }
            else cur += c;
        }
        parts.push_back(cur);
    }
    // parts[0] — числитель, остальные — знаменатель
    std::map<std::string, int> powers; // единица -> степень
    auto add_part = [&](const std::string& part, int sign) {
        // разбить по пробелам, '*', '·', '×'
        std::string cur;
        auto flush = [&]() {
            if (!cur.empty() && cur != "1") {
                // формат: база (^|**)? степень? — в Python: (.*?)(\^|\*\*)?(\d)?
                size_t p = cur.find('^');
                std::string base = cur;
                int power = 1;
                if (p != std::string::npos) {
                    base = cur.substr(0, p);
                    std::string ps = cur.substr(p + 1);
                    power = std::atoi(ps.c_str());
                }
                // обработать "**" как "^"
                p = cur.rfind("**");
                if (p != std::string::npos && (cur.find('^') == std::string::npos || p > cur.find('^'))) {
                    base = cur.substr(0, p);
                    std::string ps = cur.substr(p + 2);
                    power = std::atoi(ps.c_str());
                }
                powers[stem(base)] += sign * power;
            }
            cur.clear();
        };
        for (size_t i = 0; i < part.size(); ) {
            unsigned char ch = (unsigned char)part[i];
            if (ch == ' ' || ch == '*') { flush(); ++i; }
            else if (ch == 0xC2 && i + 1 < part.size() && (unsigned char)part[i + 1] == 0xB7) { flush(); i += 2; } // ·
            else if (ch == 0xC3 && i + 1 < part.size() && (unsigned char)part[i + 1] == 0x97) { flush(); i += 2; } // ×
            else { cur += (char)ch; ++i; }
        }
        flush();
    };
    add_part(parts[0], 1);
    for (size_t i = 1; i < parts.size(); ++i) add_part(parts[i], -1);
    std::string out;
    for (const auto& kv : powers) {
        if (kv.second == 0) continue;
        out += "U_" + kv.first;
        if (kv.second != 1) out += "^" + std::to_string(kv.second);
        out += " ";
    }
    if (out.empty()) return "1";
    out.pop_back(); // убрать хвостовой пробел
    return out;
}

// bracket(text): '3 [занятие/день]  # ...' -> (text без скобок, единица)
static std::pair<std::string, std::string> bracket(const std::string& text_in) {
    size_t start = text_in.find('[');
    if (start == std::string::npos) return {text_in, ""};
    size_t end = text_in.find(']', start);
    if (end == std::string::npos) return {text_in, ""};
    std::string inside = text_in.substr(start + 1, end - start - 1);
    std::string rest = text_in.substr(0, start) + text_in.substr(end + 1);
    return {strip_ws(rest), inside};
}

// split(): разделение величины на (числовая часть, единица) — упрощённо:
// для наших целей достаточно вернуть вид единицы по строке «число [единица]».
// Полный sympy-анализ мы не воспроизводим (это остаётся в Python);
// здесь делаем ту часть, что нужна для быстрых проверок: если в строке
// встречаются разные единицы — не считаем.
static std::pair<std::string, std::string> split_units(const std::string& q) {
    auto [body, u] = bracket(q);
    if (u.empty()) return {strip_ws(body), "1"};
    return {strip_ws(body), unit_monomial(u)};
}

// show(u): "U_час" -> "час", "1" -> "без единиц"
static std::string show(const std::string& u) {
    if (u == "1") return "без единиц";
    std::string r = u, strip_prefix = "U_";
    size_t pos = 0;
    std::string out;
    while (pos < r.size()) {
        size_t p = r.find(strip_prefix, pos);
        if (p == std::string::npos) { out += r.substr(pos); break; }
        out += r.substr(pos, p - pos);
        pos = p + strip_prefix.size();
        size_t q = r.find_first_of(" ^", pos);
        if (q == std::string::npos) q = r.size();
        out += r.substr(pos, q - pos);
        pos = q;
    }
    return out;
}

// ---- C-interop для вызова из Python ----
extern "C" {

// stem
const char* units_stem(const char* word) {
    static std::string buf;
    buf = stem(word);
    return buf.c_str();
}

// unit (моном)
const char* units_unit(const char* text) {
    static std::string buf;
    buf = unit_monomial(text);
    return buf.c_str();
}

// bracket: возвращает "текст|единица"
const char* units_bracket(const char* text) {
    static std::string buf;
    auto p = bracket(text);
    buf = p.first + "|" + p.second;
    return buf.c_str();
}

// split: возвращает "число|единица"
const char* units_split(const char* text) {
    static std::string buf;
    auto p = split_units(text);
    buf = p.first + "|" + p.second;
    return buf.c_str();
}

// show
const char* units_show(const char* u) {
    static std::string buf;
    buf = show(u);
    return buf.c_str();
}

} // extern "C"
