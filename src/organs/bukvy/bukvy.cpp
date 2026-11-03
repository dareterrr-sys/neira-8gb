// Буквенный калькулятор — «орган» Нейры для работы с буквами.
//
// Языковая модель видит не буквы, а кусочки слов (токены), поэтому ошибается в задачах вида
// «сколько букв "о" в слове обороноспособность» (work3: 3 вместо 7). Как и с калькулятором,
// мозг только пишет команду, а точный ответ считает код.
//
// Вход: по одной команде в строке, например
//     СКОЛЬКО(обороноспособность, о)
//     БУКВА(программирование, -3)
// Выход: по одной строке на команду: «команда = ответ» или «команда = ошибка: ...».
//
// Команды:
//     ДЛИНА(слово)               число букв (пробелы и знаки не считаются)
//     СКОЛЬКО(слово, буква)      сколько раз встречается буква (без учёта регистра)
//     ГЛАСНЫЕ(слово)             число гласных
//     СОГЛАСНЫЕ(слово)           число согласных (ь и ъ не считаются ни теми, ни другими)
//     СЛОГИ(слово)               число слогов = число гласных
//     БУКВА(слово, n)            n-я буква; n < 0 — считая с конца (-1 — последняя)
//     НАОБОРОТ(слово)            слово задом наперёд
//     ПАЛИНДРОМ(слово)           да/нет: читается ли одинаково в обе стороны
//     ЗАМЕНИТЬ(слово, n, буква)  заменить n-ю букву (n < 0 — с конца)
//     НОМЕР(буква)               номер буквы в русском алфавите (а = 1, ё = 7, я = 33)
//     СЛЕДУЮЩАЯ(буква)           следующая буква алфавита
//     ПРЕДЫДУЩАЯ(буква)          предыдущая буква алфавита
//
// Сборка: g++ -O2 -std=c++17 -static -o bukvy.exe bukvy.cpp

#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

using std::string;
using std::u32string;

// ---------- UTF-8 <-> кодовые точки ----------

// Раскладываем байты UTF-8 на символы Unicode. Кириллица занимает 2 байта, латиница 1.
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

// ---------- русский алфавит ----------

// Строчные буквы по порядку; ё стоит после е, как в алфавите (33 буквы).
const u32string ALPHABET = U"абвгдеёжзийклмнопрстуфхцчшщъыьэюя";
const u32string VOWELS = U"аеёиоуыэюя";

char32_t lower(char32_t c) {
    if (c >= U'А' && c <= U'Я') return c + 0x20;   // А..Я -> а..я
    if (c == U'Ё') return U'ё';
    if (c >= U'A' && c <= U'Z') return c + 0x20;
    return c;
}

bool is_letter(char32_t c) {
    c = lower(c);
    return ALPHABET.find(c) != u32string::npos || (c >= U'a' && c <= U'z');
}

bool is_vowel(char32_t c) { return VOWELS.find(lower(c)) != u32string::npos; }

// Только буквы слова (без пробелов, дефисов, кавычек и знаков ударения).
u32string letters(const u32string& w) {
    u32string out;
    for (char32_t c : w) if (is_letter(c)) out.push_back(c);
    return out;
}

// ---------- разбор команды ----------

string trim(const string& s) {
    const string spaces = " \t\r\n";
    size_t a = s.find_first_not_of(spaces), b = s.find_last_not_of(spaces);
    return a == string::npos ? "" : s.substr(a, b - a + 1);
}

// Убираем кавычки вокруг аргумента: "слово", «слово», 'слово'.
string unquote(string s) {
    s = trim(s);
    const std::vector<std::pair<string, string>> pairs = {{"\"", "\""}, {"'", "'"}, {"«", "»"}};
    for (auto& [l, r] : pairs)
        if (s.size() >= l.size() + r.size() && s.compare(0, l.size(), l) == 0 &&
            s.compare(s.size() - r.size(), r.size(), r) == 0)
            return trim(s.substr(l.size(), s.size() - l.size() - r.size()));
    return s;
}

struct Error { string what; };

long to_int(const string& s) {
    try {
        size_t used = 0;
        long v = std::stol(trim(s), &used);
        if (used != trim(s).size()) throw 0;
        return v;
    } catch (...) { throw Error{"номер должен быть целым числом: " + s}; }
}

char32_t one_letter(const string& s) {
    u32string l = letters(decode(unquote(s)));
    if (l.size() != 1) throw Error{"нужна ровно одна буква: " + s};
    return lower(l[0]);
}

// n-я позиция: 1..len или -1..-len (с конца). Возвращает индекс с нуля.
size_t position(long n, size_t len) {
    if (n == 0 || (n > 0 && size_t(n) > len) || (n < 0 && size_t(-n) > len))
        throw Error{"длина слова " + std::to_string(len) + ", позиции " + std::to_string(n) + " нет"};
    return n > 0 ? size_t(n - 1) : len - size_t(-n);
}

string run(const string& name, const std::vector<string>& args) {
    auto need = [&](size_t n) {
        if (args.size() != n) throw Error{name + " ждёт аргументов: " + std::to_string(n)};
    };
    auto word = [&](size_t i) { return letters(decode(unquote(args[i]))); };

    if (name == "ДЛИНА") { need(1); return std::to_string(word(0).size()); }
    if (name == "СКОЛЬКО") {
        need(2);
        char32_t b = one_letter(args[1]);
        long n = 0;
        for (char32_t c : word(0)) n += lower(c) == b;
        return std::to_string(n);
    }
    if (name == "ГЛАСНЫЕ" || name == "СЛОГИ") {
        need(1);
        long n = 0;
        for (char32_t c : word(0)) n += is_vowel(c);
        return std::to_string(n);
    }
    if (name == "СОГЛАСНЫЕ") {
        need(1);
        long n = 0;
        for (char32_t c : word(0)) n += !is_vowel(c) && lower(c) != U'ь' && lower(c) != U'ъ';
        return std::to_string(n);
    }
    if (name == "БУКВА") {
        need(2);
        u32string w = word(0);
        return encode(u32string(1, lower(w[position(to_int(args[1]), w.size())])));
    }
    if (name == "НАОБОРОТ") {
        need(1);
        u32string w = word(0);
        return encode(u32string(w.rbegin(), w.rend()));
    }
    if (name == "ПАЛИНДРОМ") {
        need(1);
        u32string w;
        for (char32_t c : word(0)) w.push_back(lower(c));
        return u32string(w.rbegin(), w.rend()) == w ? "да" : "нет";
    }
    if (name == "ЗАМЕНИТЬ") {
        need(3);
        u32string w = word(0);
        w[position(to_int(args[1]), w.size())] = one_letter(args[2]);
        return encode(w);
    }
    if (name == "НОМЕР" || name == "СЛЕДУЮЩАЯ" || name == "ПРЕДЫДУЩАЯ") {
        need(1);
        char32_t b = one_letter(args[0]);
        size_t i = ALPHABET.find(b);
        if (i == u32string::npos) throw Error{"это не буква русского алфавита: " + args[0]};
        if (name == "НОМЕР") return std::to_string(i + 1);
        if (name == "СЛЕДУЮЩАЯ") {
            if (i + 1 == ALPHABET.size()) throw Error{"я — последняя буква алфавита"};
            return encode(u32string(1, ALPHABET[i + 1]));
        }
        if (i == 0) throw Error{"а — первая буква алфавита"};
        return encode(u32string(1, ALPHABET[i - 1]));
    }
    throw Error{"неизвестная команда: " + name};
}

// Делим аргументы по запятым, не трогая запятые внутри кавычек.
std::vector<string> split_args(const string& s) {
    std::vector<string> out;
    string cur;
    bool quote = false;
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '"') quote = !quote;
        if (s.compare(i, 2, "«") == 0) quote = true;
        if (s.compare(i, 2, "»") == 0) quote = false;
        if (s[i] == ',' && !quote) { out.push_back(cur); cur.clear(); }
        else cur += s[i];
    }
    if (!trim(cur).empty() || !out.empty()) out.push_back(cur);
    return out;
}

int main() {
    std::ios::sync_with_stdio(false);
    string line;
    while (std::getline(std::cin, line)) {
        line = trim(line);
        if (line.empty()) continue;
        size_t open = line.find('('), close = line.rfind(')');
        if (open == string::npos || close == string::npos || close < open) {
            std::cout << line << " = ошибка: нужно КОМАНДА(аргументы)\n";
            continue;
        }
        // Имя команды переводим в верхний регистр, чтобы «длина(...)» тоже работала.
        u32string name32 = decode(trim(line.substr(0, open)));
        for (char32_t& c : name32) {
            if (c >= U'а' && c <= U'я') c -= 0x20;
            else if (c == U'ё') c = U'Ё';
        }
        // Сначала считаем ответ, потом печатаем: иначе при ошибке начало строки уже было бы выведено.
        string answer;
        try {
            answer = run(encode(name32), split_args(line.substr(open + 1, close - open - 1)));
        } catch (const Error& e) {
            answer = "ошибка: " + e.what;
        }
        std::cout << line << " = " << answer << "\n";
    }
    return 0;
}
