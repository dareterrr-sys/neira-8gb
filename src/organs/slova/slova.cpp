// Текстовый калькулятор — «орган» Нейры для работы со словами и текстами (пара к буквенному bukvy.exe).
//
// Языковая модель видит не буквы и слова, а кусочки слов (токены), поэтому ошибается, когда нужно точно
// посчитать слова, найти подстроку, выписать n-е слово или расставить слова по алфавиту. Как с калькулятором:
// мозг только пишет команду, точный ответ считает код.
//
// Вход: по одной команде в строке, аргументы в кавычках ("..." или «...») через запятую, числа без кавычек:
//     ВХОЖДЕНИЯ("Карл у Клары украл кораллы", "кл")
//     СЛОВО("На дворе трава, на траве дрова", -1)
// Выход: по одной строке на команду: «команда = ответ» или «команда = ошибка: ...».
//
// Команды (регистр букв не важен, ё и е различаются):
//     СЛОВА(текст)                   число слов («по-русски» — одно слово, числа тоже слова)
//     ПРЕДЛОЖЕНИЯ(текст)             число предложений (по . ! ? …)
//     СИМВОЛЫ(текст)                 число символов вместе с пробелами
//     БУКВЫ(текст)                   число букв во всём тексте
//     ВХОЖДЕНИЯ(текст, подстрока)    сколько раз встречается подстрока (без наложений)
//     ПОЗИЦИЯ(текст, подстрока)      номер символа, с которого начинается первое вхождение (с 1); 0 — нет
//     СЛОВО(текст, n)                n-е слово; n < 0 — считая с конца
//     ДЛИННОЕ(текст)                 самое длинное слово (первое из равных)
//     КОРОТКОЕ(текст)                самое короткое слово
//     АЛФАВИТ(текст)                 слова по алфавиту (ё после е)
//     ЧАСТОЕ(текст)                  самое частое слово и сколько раз: «слово: n»
//     НАЧИНАЮТСЯ(текст, буквы)       сколько слов начинаются с этих букв
//     ОКАНЧИВАЮТСЯ(текст, буквы)     сколько слов оканчиваются на эти буквы
//     ПОРЯДОК(текст)                 слова в обратном порядке
//     АНАГРАММА(слово1, слово2)      да/нет: из одних ли букв (пробелы и регистр не важны)
//     ОДИНАКОВЫ(текст1, текст2)      да/нет: совпадают ли тексты без учёта регистра и лишних пробелов
//
// Сборка: g++ -O2 -std=c++17 -static -o slova.exe slova.cpp

#include <algorithm>
#include <iostream>
#include <map>
#include <string>
#include <vector>

using std::string;
using std::u32string;
using std::vector;

// ---------- UTF-8 <-> кодовые точки (как в bukvy.cpp) ----------

u32string decode(const string& s) {
    u32string out;
    for (size_t i = 0; i < s.size();) {
        unsigned char c = s[i];
        char32_t cp;
        int len;
        if (c < 0x80) { cp = c; len = 1; }
        else if ((c >> 5) == 0x6) { cp = c & 0x1F; len = 2; }
        else if ((c >> 4) == 0xE) { cp = c & 0x0F; len = 3; }
        else { cp = c & 0x07; len = 4; }
        for (int k = 1; k < len && i + k < s.size(); ++k) cp = (cp << 6) | (s[i + k] & 0x3F);
        out.push_back(cp);
        i += len;
    }
    return out;
}

string encode(const u32string& s) {
    string out;
    for (char32_t cp : s) {
        if (cp < 0x80) out += char(cp);
        else if (cp < 0x800) { out += char(0xC0 | (cp >> 6)); out += char(0x80 | (cp & 0x3F)); }
        else if (cp < 0x10000) {
            out += char(0xE0 | (cp >> 12)); out += char(0x80 | ((cp >> 6) & 0x3F)); out += char(0x80 | (cp & 0x3F));
        } else {
            out += char(0xF0 | (cp >> 18)); out += char(0x80 | ((cp >> 12) & 0x3F));
            out += char(0x80 | ((cp >> 6) & 0x3F)); out += char(0x80 | (cp & 0x3F));
        }
    }
    return out;
}

// ---------- буквы ----------

const char32_t YO = 0x451, YO_CAP = 0x401;   // ё, Ё

char32_t lower(char32_t c) {
    if (c >= 0x410 && c <= 0x42F) return c + 0x20;   // А-Я -> а-я
    if (c == YO_CAP) return YO;
    if (c >= 'A' && c <= 'Z') return c + 32;
    return c;
}

bool is_letter(char32_t c) {
    c = lower(c);
    return (c >= 0x430 && c <= 0x44F) || c == YO || (c >= 'a' && c <= 'z');
}

bool is_word_char(char32_t c) { return is_letter(c) || (c >= '0' && c <= '9'); }

u32string lower(u32string s) {
    for (auto& c : s) c = lower(c);
    return s;
}

// порядок для алфавита: ё сразу после е
int rank(char32_t c) {
    c = lower(c);
    if (c == YO) return 0x435 * 2 + 1;
    return int(c) * 2;
}

bool alpha_less(const u32string& a, const u32string& b) {
    for (size_t i = 0; i < a.size() && i < b.size(); ++i) {
        int ra = rank(a[i]), rb = rank(b[i]);
        if (ra != rb) return ra < rb;
    }
    return a.size() < b.size();
}

// слова: буквы и цифры; дефис и апостроф внутри слова («по-русски», «O'Neil») слово не рвут
vector<u32string> words(const u32string& t) {
    vector<u32string> out;
    u32string cur;
    for (size_t i = 0; i < t.size(); ++i) {
        char32_t c = t[i];
        bool inner = (c == '-' || c == '\'' || c == 0x2019) && !cur.empty() && i + 1 < t.size() && is_word_char(t[i + 1]);
        if (is_word_char(c) || inner) cur.push_back(c);
        else if (!cur.empty()) { out.push_back(cur); cur.clear(); }
    }
    if (!cur.empty()) out.push_back(cur);
    return out;
}

// ---------- разбор команды ----------

struct Call {
    string name;
    vector<u32string> args;
};

string trim(const string& s) {
    size_t a = s.find_first_not_of(" \t\r\n"), b = s.find_last_not_of(" \t\r\n");
    return a == string::npos ? "" : s.substr(a, b - a + 1);
}

// КОМАНДА("текст, с запятыми", "x", -1): аргумент в кавычках может содержать запятые
bool parse(const string& line, Call& call, string& err) {
    size_t open = line.find('('), close = line.rfind(')');
    if (open == string::npos || close == string::npos || close < open) { err = "нет скобок"; return false; }
    call.name = trim(line.substr(0, open));
    u32string body = decode(line.substr(open + 1, close - open - 1));
    u32string cur;
    bool quoted = false, had_quote = false;
    char32_t closing = 0;
    for (char32_t c : body) {
        if (!quoted && (c == '"' || c == 0xAB || c == 0x201C)) {   // " « “
            quoted = true; had_quote = true;
            closing = c == 0xAB ? 0xBB : (c == 0x201C ? 0x201D : '"');
            cur.clear();   // пробел перед кавычкой — не часть аргумента

            continue;
        }
        if (quoted && c == closing) { quoted = false; continue; }
        if (!quoted && c == ',') {
            string a = trim(encode(cur));
            call.args.push_back(decode(a));
            cur.clear(); had_quote = false;
            continue;
        }
        cur.push_back(c);
    }
    if (quoted) { err = "незакрытая кавычка"; return false; }
    string last = had_quote ? encode(cur) : trim(encode(cur));
    if (!last.empty() || !call.args.empty()) call.args.push_back(decode(had_quote ? last : trim(last)));
    return true;
}

long to_int(const u32string& s) {
    string t = trim(encode(s));
    size_t pos = 0;
    long v = std::stol(t, &pos);
    if (pos != t.size()) throw std::invalid_argument("не число");
    return v;
}

string join(const vector<u32string>& ws) {
    string out;
    for (size_t i = 0; i < ws.size(); ++i) out += (i ? " " : "") + encode(ws[i]);
    return out;
}

// ---------- команды ----------

string run(const Call& c) {
    auto need = [&](size_t n) {
        if (c.args.size() != n) throw std::invalid_argument("нужно аргументов: " + std::to_string(n));
    };
    const string& n = c.name;
    if (n == "СЛОВА") { need(1); return std::to_string(words(c.args[0]).size()); }
    if (n == "СИМВОЛЫ") { need(1); return std::to_string(c.args[0].size()); }
    if (n == "БУКВЫ") {
        need(1);
        return std::to_string(std::count_if(c.args[0].begin(), c.args[0].end(), [](char32_t ch) { return is_letter(ch); }));
    }
    if (n == "ПРЕДЛОЖЕНИЯ") {
        need(1);
        const u32string& t = c.args[0];
        long count = 0;
        bool content = false;   // есть ли слова после последнего конца предложения
        for (size_t i = 0; i < t.size(); ++i) {
            char32_t ch = t[i];
            if (is_word_char(ch)) content = true;
            if ((ch == '.' || ch == '!' || ch == '?' || ch == 0x2026) && content) {
                while (i + 1 < t.size() && (t[i + 1] == '.' || t[i + 1] == '!' || t[i + 1] == '?' || t[i + 1] == 0x2026)) ++i;
                ++count; content = false;
            }
        }
        if (content) ++count;
        return std::to_string(count);
    }
    if (n == "ВХОЖДЕНИЯ" || n == "ПОЗИЦИЯ") {
        need(2);
        u32string t = lower(c.args[0]), p = lower(c.args[1]);
        if (p.empty()) throw std::invalid_argument("пустая подстрока");
        size_t pos = t.find(p);
        if (n == "ПОЗИЦИЯ") return std::to_string(pos == u32string::npos ? 0 : pos + 1);
        long count = 0;
        while (pos != u32string::npos) { ++count; pos = t.find(p, pos + p.size()); }
        return std::to_string(count);
    }
    if (n == "СЛОВО") {
        need(2);
        auto ws = words(c.args[0]);
        long k = to_int(c.args[1]);
        long idx = k > 0 ? k - 1 : long(ws.size()) + k;
        if (k == 0 || idx < 0 || idx >= long(ws.size()))
            throw std::invalid_argument("в тексте " + std::to_string(ws.size()) + " слов");
        return encode(ws[idx]);
    }
    if (n == "ДЛИННОЕ" || n == "КОРОТКОЕ") {
        need(1);
        auto ws = words(c.args[0]);
        if (ws.empty()) throw std::invalid_argument("нет слов");
        u32string best = ws[0];
        for (auto& w : ws)
            if (n == "ДЛИННОЕ" ? w.size() > best.size() : w.size() < best.size()) best = w;
        return encode(best);
    }
    if (n == "АЛФАВИТ") {
        need(1);
        auto ws = words(c.args[0]);
        std::stable_sort(ws.begin(), ws.end(), [](const u32string& a, const u32string& b) { return alpha_less(a, b); });
        return join(ws);
    }
    if (n == "ЧАСТОЕ") {
        need(1);
        auto ws = words(c.args[0]);
        if (ws.empty()) throw std::invalid_argument("нет слов");
        std::map<u32string, long> freq;
        vector<u32string> order;
        for (auto& w : ws) {
            auto lw = lower(w);
            if (!freq.count(lw)) order.push_back(lw);
            ++freq[lw];
        }
        u32string best = order[0];
        for (auto& w : order) if (freq[w] > freq[best]) best = w;
        return encode(best) + ": " + std::to_string(freq[best]);
    }
    if (n == "НАЧИНАЮТСЯ" || n == "ОКАНЧИВАЮТСЯ") {
        need(2);
        u32string p = lower(c.args[1]);
        long count = 0;
        for (auto& w : words(c.args[0])) {
            auto lw = lower(w);
            if (lw.size() < p.size()) continue;
            if (n == "НАЧИНАЮТСЯ" ? lw.compare(0, p.size(), p) == 0 : lw.compare(lw.size() - p.size(), p.size(), p) == 0)
                ++count;
        }
        return std::to_string(count);
    }
    if (n == "ПОРЯДОК") {
        need(1);
        auto ws = words(c.args[0]);
        std::reverse(ws.begin(), ws.end());
        return join(ws);
    }
    if (n == "АНАГРАММА") {
        need(2);
        auto letters = [](const u32string& s) {
            u32string out;
            for (char32_t ch : s) if (is_letter(ch)) out.push_back(lower(ch));
            std::sort(out.begin(), out.end());
            return out;
        };
        return letters(c.args[0]) == letters(c.args[1]) ? "да" : "нет";
    }
    if (n == "ОДИНАКОВЫ") {
        need(2);
        auto norm = [](const u32string& s) { return lower(s.empty() ? s : decode(join(words(s)))); };
        return norm(c.args[0]) == norm(c.args[1]) ? "да" : "нет";
    }
    throw std::invalid_argument("неизвестная команда " + n);
}

int main() {
    std::ios::sync_with_stdio(false);
    string line;
    while (std::getline(std::cin, line)) {
        line = trim(line);
        if (line.empty()) continue;
        Call call;
        string err;
        if (!parse(line, call, err)) { std::cout << line << " = ошибка: " << err << "\n"; continue; }
        try {
            string result = run(call);   // сначала посчитать: при ошибке начало строки не должно уйти в вывод
            std::cout << line << " = " << result << "\n";
        } catch (const std::exception& e) {
            std::cout << line << " = ошибка: " << e.what() << "\n";
        }
    }
    return 0;
}
