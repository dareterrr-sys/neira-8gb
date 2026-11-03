// Русский язык — «орган» Нейры для заданий ЕГЭ, которые решает словарь, а не рассуждение (просьба автора, 27.10:
// «чтобы ЕГЭ по русскому норм прошло», «пусть у Нейры будет огромный словарный запас», «органы на C++»).
//
// Модель видит кусочки слов, а не буквы, и путает ударения и пропущенные буквы. Человек в таких случаях смотрит
// в словарь — орган делает то же самое по трём словарям:
//     opencorpora.bin  — 3 млн словоформ OpenCorpora (через pymorphy3-dicts-ru), маршрут А для букв;
//     ru_RU.aff/.dic   — Hunspell (словарь LibreOffice), маршрут Б для букв — другой словарь и другой код;
//     fipi_stress.txt  — «Орфоэпический список — 2026» ФИПИ (+ слова прошлых лет), маршрут А для ударений;
//     accents.bin      — 3.2 млн словоформ с ударениями из RUAccent, маршрут Б для ударений.
// Ответ выдаётся, только если оба маршрута согласны; иначе — «не знаю: ...» (лучше честное «не знаю», чем уверенная
// ошибка). Правило ФИПИ: буква Ё в задании 4 может быть написана как Е.
//
// Вход: по одной команде в строке (программа работает, пока не закончится ввод — можно держать открытой):
//     ЕСТЬ("слово")                    какие словари знают слово
//     УДАРЕНИЕ("звонИт")               верно / неверно / не знаю (прописная буква — ударная)
//     БУКВА("р..сток")                 какая буква пропущена: «о» или «не знаю: А о,а; Б о»
//     ЗАДАНИЕ(4, "текст задания")      номера верных вариантов, например «125»
//     ЗАДАНИЕ(9|10|11|12, "текст")     номера рядов, где пропущена одна и та же буква
//     ЗАДАНИЕ(15, "текст")             номера, где пишется НН (или Н — как спрошено)
//     (13 и 14 — отложены, см. ЗАДАНИЕ в run; РАЗБОР и НАПИСАНИЕ — отладка правил)
// Выход: по строке на команду: «КОМАНДА = ответ».
//
// Сборка (MSYS2 ucrt64): g++ -O2 -std=c++17 -static -DHUNSPELL_STATIC -o russkiy.exe russkiy.cpp -lhunspell-1.7

#include <hunspell/hunspell.hxx>

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <type_traits>
#include <vector>

using std::string;
using std::u32string;
using std::vector;

// ---------- UTF-8 <-> кодовые точки ----------

u32string decode(const string& s) {
    u32string out;
    for (size_t i = 0; i < s.size();) {
        unsigned char c = s[i];
        char32_t cp;
        int n;
        if (c < 0x80) { cp = c; n = 1; }
        else if ((c >> 5) == 6) { cp = c & 0x1F; n = 2; }
        else if ((c >> 4) == 14) { cp = c & 0x0F; n = 3; }
        else { cp = c & 0x07; n = 4; }
        for (int k = 1; k < n && i + k < s.size(); k++) cp = (cp << 6) | (s[i + k] & 0x3F);
        out += cp;
        i += n;
    }
    return out;
}

string encode(const u32string& s) {
    string out;
    for (char32_t c : s) {
        if (c < 0x80) out += (char)c;
        else if (c < 0x800) { out += (char)(0xC0 | (c >> 6)); out += (char)(0x80 | (c & 0x3F)); }
        else if (c < 0x10000) {
            out += (char)(0xE0 | (c >> 12)); out += (char)(0x80 | ((c >> 6) & 0x3F)); out += (char)(0x80 | (c & 0x3F));
        } else {
            out += (char)(0xF0 | (c >> 18)); out += (char)(0x80 | ((c >> 12) & 0x3F));
            out += (char)(0x80 | ((c >> 6) & 0x3F)); out += (char)(0x80 | (c & 0x3F));
        }
    }
    return out;
}

bool is_upper(char32_t c) { return (c >= U'А' && c <= U'Я') || c == U'Ё'; }
bool is_lower(char32_t c) { return (c >= U'а' && c <= U'я') || c == U'ё'; }
bool is_cyr(char32_t c) { return is_upper(c) || is_lower(c); }
char32_t lower(char32_t c) {
    if (c >= U'А' && c <= U'Я') return c + 0x20;
    if (c == U'Ё') return U'ё';
    return c;
}
u32string lower(u32string s) { for (auto& c : s) c = lower(c); return s; }
bool is_vowel(char32_t c) { return u32string(U"аеёиоуыэюя").find(lower(c)) != u32string::npos; }

// кодовая точка -> байт cp1251 (только то, что бывает в словах словарей); 0 — нет такого
unsigned char cp1251(char32_t c) {
    if (c >= U'А' && c <= U'я') return (unsigned char)(0xC0 + (c - U'А'));
    if (c == U'ё') return 0xB8;
    if (c == U'Ё') return 0xA8;
    if (c == U'-') return '-';
    return 0;
}

bool to_cp1251(const u32string& w, string& out) {
    out.clear();
    for (char32_t c : w) {
        unsigned char b = cp1251(c);
        if (!b) return false;
        out += (char)b;
    }
    return true;
}

// ---------- упакованный словарь: uint32 N, uint32 offsets[N+1], слитные байты, отсортировано ----------

struct Packed {
    vector<uint32_t> off;
    string blob;
    uint32_t n = 0;
    bool load(const string& path) {
        FILE* f = fopen(path.c_str(), "rb");
        if (!f) return false;
        if (fread(&n, 4, 1, f) != 1) { fclose(f); return false; }
        off.resize(n + 1);
        if (fread(off.data(), 4, n + 1, f) != n + 1) { fclose(f); return false; }
        blob.resize(off[n]);
        size_t got = fread(&blob[0], 1, off[n], f);
        fclose(f);
        return got == off[n];
    }
    // запись i до байта 0 (ключ) и после него (данные)
    std::pair<string, string> entry(uint32_t i) const {
        string e = blob.substr(off[i], off[i + 1] - off[i]);
        size_t z = e.find('\0');
        if (z == string::npos) return {e, ""};
        return {e.substr(0, z), e.substr(z + 1)};
    }
    // ищет ключ; возвращает индекс или -1
    long find(const string& key) const {
        uint32_t lo = 0, hi = n;
        while (lo < hi) {
            uint32_t mid = (lo + hi) / 2;
            string k = entry(mid).first;
            int c = memcmp(k.data(), key.data(), std::min(k.size(), key.size()));
            if (c == 0) c = (k.size() < key.size()) ? -1 : (k.size() > key.size() ? 1 : 0);
            if (c == 0) return mid;
            if (c < 0) lo = mid + 1; else hi = mid;
        }
        return -1;
    }
};

// ---------- словари ----------

string DATA = "data";
Packed OC, ACC, YO;
std::unique_ptr<Hunspell> HUN;
// ФИПИ: слово без ударения (ё -> е) -> позиции ударения (с 0), с учётом ё
std::map<u32string, std::set<int>> FIPI;

u32string yo_to_e(u32string w) { for (auto& c : w) if (c == U'ё') c = U'е'; return w; }

bool load_all() {
    if (!OC.load(DATA + "/opencorpora.bin")) { std::cerr << "нет " << DATA << "/opencorpora.bin\n"; return false; }
    if (!ACC.load(DATA + "/accents.bin")) { std::cerr << "нет " << DATA << "/accents.bin\n"; return false; }
    YO.load(DATA + "/yo.bin");
    HUN.reset(new Hunspell((DATA + "/ru_RU.aff").c_str(), (DATA + "/ru_RU.dic").c_str()));
    for (const char* name : {"/fipi_stress.txt", "/fipi_stress_old.txt"}) {
        FILE* f = fopen((DATA + name).c_str(), "rb");
        if (!f) continue;
        char buf[256];
        while (fgets(buf, sizeof buf, f)) {
            u32string w = decode(buf);
            while (!w.empty() && !is_cyr(w.back())) w.pop_back();
            int pos = -1, ups = 0;
            for (size_t i = 0; i < w.size(); i++) if (is_upper(w[i])) { pos = (int)i; ups++; }
            if (ups != 1) continue;
            FIPI[yo_to_e(lower(w))].insert(pos);
        }
        fclose(f);
    }
    return true;
}

bool in_oc(const u32string& w) {
    string k;
    return to_cp1251(lower(w), k) && OC.find(k) >= 0;
}

// Hunspell различает регистр: имена собственные («Вьетнам») — с прописной
bool in_hun(const u32string& w) {
    if (!HUN) return false;
    u32string lw = lower(w);
    if (HUN->spell(encode(lw))) return true;
    if (!lw.empty() && lw[0] >= U'а' && lw[0] <= U'я') { lw[0] -= 0x20; return HUN->spell(encode(lw)); }
    return false;
}

// грамматические пометы OpenCorpora (build_data.py, oc_flags), по всем разборам слова; -1 — нет слова
enum : int {
    V3SG = 1, V3PL = 2, NOM_SG = 4, NOM_PL = 8, ACCS = 16, V2SG = 32, ABLT = 64, GENT = 128,   // байт 0
    VERB = 1 << 8, GRND = 2 << 8, PRTF = 4 << 8, PRTS = 8 << 8, ADJF = 16 << 8, ADJS = 32 << 8,  // байт 1
    NOUN = 64 << 8, ADVB = 128 << 8,
    COMP = 1 << 16, NPRO = 2 << 16, NUMR = 4 << 16, PREP = 8 << 16, CONJ = 16 << 16, PRCL = 32 << 16,  // байт 2
    PRED = 64 << 16, DATV = 128 << 16,
};
int oc_flags(const u32string& w) {
    string k;
    if (!to_cp1251(lower(w), k)) return -1;
    long i = OC.find(k);
    if (i < 0) return -1;
    string d = OC.entry((uint32_t)i).second;
    int f = 0;
    for (size_t j = 0; j < d.size() && j < 3; j++) f |= (int)(unsigned char)d[j] << (8 * j);
    return f;
}

// RUAccent: позиции ударения (с 0) слова как написано; пусто — нет в словаре
std::set<int> acc_stress(const u32string& w) {
    std::set<int> out;
    string k;
    if (!to_cp1251(lower(w), k)) return out;
    long i = ACC.find(k);
    if (i < 0) return out;
    for (unsigned char p : ACC.entry((uint32_t)i).second) out.insert((int)p - 1);
    u32string lw = lower(w);
    for (size_t j = 0; j < lw.size(); j++) if (lw[j] == U'ё') { out.clear(); out.insert((int)j); }  // ё всегда ударная
    return out;
}

// ---------- ударение ----------

// 1 — верно, 0 — неверно, -1 — не знаю; why — пояснение
int stress_ok(const u32string& written, string& why) {
    int pos = -1, ups = 0;
    for (size_t i = 0; i < written.size(); i++) if (is_upper(written[i])) { pos = (int)i; ups++; }
    if (ups != 1 || !is_vowel(written[pos])) { why = "не вижу ударную (одна прописная гласная)"; return -1; }
    u32string lw = lower(written);
    // маршрут А: список ФИПИ (ё и е не различаем — так в КИМ)
    int a = -1;
    auto it = FIPI.find(yo_to_e(lw));
    if (it != FIPI.end()) {
        if (it->second.size() == 1) a = it->second.count(pos) ? 1 : 0;
        else why = "в списке ФИПИ два ударения (омограф)";
    }
    // маршрут Б: RUAccent; если в написании е вместо ё — пробуем ё на каждом месте е
    std::set<int> b = acc_stress(lw);
    for (size_t j = 0; b.empty() && j < lw.size(); j++)
        if (lw[j] == U'е') { u32string v = lw; v[j] = U'ё'; b = acc_stress(v); }
    int bv = -1;
    if (b.size() == 1) bv = b.count(pos) ? 1 : 0;
    else if (b.size() > 1 && !b.count(pos)) bv = 0;  // ни один вариант не совпал — неверно
    // слово из списка ФИПИ: список — это и есть ключ экзамена, он решает (RUAccent расходится с ним в 2 словах из
    // 290 — «налилА», «понялА», где RUAccent допускает разговорное ударение)
    if (a >= 0) return a;
    if (bv >= 0) { why = "есть только в RUAccent"; return -2 - bv; }
    if (why.empty()) why = "слова нет в словарях";
    return -1;
}

// ---------- пропущенная буква ----------

bool in_acc(const u32string& w) { return !acc_stress(w).empty(); }

// что бывает на месте пропуска в заданиях 9-12: гласные, ъ/ь, з/с и д/т на конце приставок; U'\0' — ничего.
// Другие согласные не орфограммы этих заданий: «не..данная (работа)» — «несданная», а не «нежданная»
const u32string LETTERS = U"аеёиоуыэюяъьздст";

// ё на месте е по словарю ё-слов RUAccent: «сгущенка» -> позиции ё; пусто — не ё-слово
std::set<int> yo_pos(const u32string& w) {
    std::set<int> out;
    string k;
    if (!to_cp1251(lower(w), k)) return out;
    long i = YO.n ? YO.find(k) : -1;
    if (i < 0) return out;
    for (unsigned char p : YO.entry((uint32_t)i).second) out.insert((int)p - 1);
    return out;
}

std::set<char32_t> fills(const u32string& w, bool (*known)(const u32string&)) {
    std::set<char32_t> out;
    size_t g = w.find(U"..");
    if (g == u32string::npos) return out;
    u32string head = w.substr(0, g), tail = w.substr(g + 2);
    if (known(head + tail)) out.insert(U'\0');
    for (char32_t c : LETTERS) if (known(head + c + tail)) out.insert(c);
    return out;
}

string show(const std::set<char32_t>& s) {
    if (s.empty()) return "нет слова";
    string out;
    for (char32_t c : s) { if (!out.empty()) out += ","; out += c ? encode(u32string(1, c)) : "∅"; }
    return out;
}

// орфограмма ЕГЭ — безударный звук: гласную под ударением («помнЁшь» вместо «помнишь») отбрасываем; кроме о/ё/е
// после шипящих и ц — там ударная гласная и есть орфограмма
void drop_stressed(const u32string& w, std::set<char32_t>& s) {
    size_t g = w.find(U"..");
    if (g == u32string::npos || (g && u32string(U"жшчщц").find(lower(w[g - 1])) != u32string::npos)) return;
    for (auto it = s.begin(); it != s.end();) {
        if (*it && is_vowel(*it)) {
            auto st = acc_stress(w.substr(0, g) + *it + w.substr(g + 2));
            if (st.size() == 1 && *st.begin() == (int)g) { it = s.erase(it); continue; }
        }
        ++it;
    }
}

// «ничего не пишется» — только в паре с ъ/ь («застлать» не ответ на «заст..лать») или перед к («рез..кий» —
// резкий, к/ск); одно ∅ в другом месте — скорее нужного слова нет в словарях («не..битая» — несбитая)
void drop_empty(const u32string& w, std::set<char32_t>& s) {
    if (!s.count(U'\0')) return;
    size_t g = w.find(U"..");
    bool before_k = g != u32string::npos && g + 2 < w.size() && w[g + 2] == U'к';
    if (s.count(U'ъ') || s.count(U'ь')) return;
    if (before_k) return;
    s.erase(U'\0');
}

// после шипящих и ц ударное е словари часто пишут вместо ё («перченый» вместо «перчёный»): ё по словарю ё-слов,
// иначе е под ударением — «е или ё»
void fix_yo(const u32string& w, std::set<char32_t>& s) {
    size_t g = w.find(U"..");
    if (g == u32string::npos || !s.count(U'е')) return;
    u32string e = w.substr(0, g) + U'е' + w.substr(g + 2);
    if (yo_pos(e).count((int)g)) { s.erase(U'е'); s.insert(U'ё'); return; }
    if (g && u32string(U"жшчщц").find(lower(w[g - 1])) != u32string::npos) {
        auto st = acc_stress(e);
        if (st.size() == 1 && *st.begin() == (int)g) s.insert(U'ё');
        if (g + 2 < w.size() && w[g + 2] == U'н') s.insert(U'ё');  // -ён-/-ен-: «перч..ный» — перчёный
    }
}

// о/ё после шипящих перед -в- (-ов-/-ёв-): словари отстают от правил 2006 г. («мелочёвка» вместо «мелочовка») —
// если словари дают ё, допускаем и о
void fix_ov(const u32string& w, std::set<char32_t>& s) {
    size_t g = w.find(U"..");
    if (g == u32string::npos || !g || !s.count(U'ё')) return;
    if (u32string(U"жшчщц").find(lower(w[g - 1])) == u32string::npos) return;
    if (g + 2 < w.size() && w[g + 2] == U'в') s.insert(U'о');
}

struct Fill {
    std::set<char32_t> s;  // возможные буквы
    bool single = false;   // по одному словарю (RUAccent), оба основных слова не знают
    string why;
};

// буквы, при которых слово есть в ОБОИХ словарях (А и Б); если ни при какой — по третьему (RUAccent)
Fill candidates(const u32string& w) {
    Fill f;
    size_t lb = w.find(U'[');
    if (lb != u32string::npos && lb + 2 < w.size() && w[lb + 2] == U']') {  // буква выбрана по смыслу (мозгом)
        f.s.insert(w[lb + 1]);
        f.why = encode(w) + ": выбрано по смыслу";
        return f;
    }
    auto a = fills(w, in_oc), b = fills(w, in_hun);
    for (auto c : a) if (b.count(c)) f.s.insert(c);
    drop_empty(w, f.s);
    drop_stressed(w, f.s);
    if (f.s.empty()) {
        f.s = fills(w, in_acc);
        drop_empty(w, f.s);
        drop_stressed(w, f.s);
        f.single = !f.s.empty();
    }
    fix_yo(w, f.s);
    fix_ov(w, f.s);
    f.why = encode(w) + ": А " + show(a) + "; Б " + show(b) + (f.single ? "; RUAccent " + show(f.s) : "");
    return f;
}

// число подлежащего по подсказке в скобках: 'S', 'P' или 0 (не понять). Сначала слова, которые не бывают
// винительным падежом («(друзья) выкро..т (время)» — подлежащее «друзья»), потом все
char hint_number(const vector<u32string>& hints) {
    for (int pass = 0; pass < 2; pass++) {
        bool sg = false, pl = false;
        for (auto& h : hints) {
            int f = oc_flags(h);
            if (f < 0 || (pass == 0 && (f & 16))) continue;
            sg |= (f & 4) != 0;
            pl |= (f & 8) != 0;
        }
        if (sg != pl) return sg ? 'S' : 'P';
        if (sg && pl) return 0;
    }
    return 0;
}

// глагол с пропуском и подсказкой: оставляем буквы, при которых число глагола совпадает с числом подсказки
void by_number(const u32string& w, char num, std::set<char32_t>& s) {
    if (!num || s.size() < 2) return;
    size_t g = w.find(U"..");
    std::set<char32_t> keep;
    for (char32_t c : s) {
        int f = oc_flags(w.substr(0, g) + (c ? u32string(1, c) : U"") + w.substr(g + 2));
        if (f > 0 && (f & (num == 'S' ? 1 : 2))) keep.insert(c);
    }
    if (!keep.empty()) s = keep;
}

// буква по словарям для команды БУКВА; U'?' — не знаю
char32_t letter(const u32string& w, string& why) {
    Fill f = candidates(w);
    if (f.s.size() == 1) { if (f.single) why = "один источник"; return *f.s.begin(); }
    why = f.why;
    return U'?';
}

// ---------- разбор задания ----------

// убирает знаки ударения (U+0301) и мягкие переносы; пропуск «…», «...», «_» -> «..»
u32string clean(u32string t) {
    u32string out;
    for (char32_t c : t) {
        if (c == 0x301 || c == 0xAD) continue;
        if (c == U'…' || c == U'_') c = U'.';
        static const u32string lat = U"aeopcxyAEOPCXHKMTB", cyr = U"аеорсхуАЕОРСХНКМТВ";
        size_t li = lat.find(c);
        if (li != u32string::npos) {  // латинская буква-двойник рядом с русской — русская
            bool near = (!out.empty() && is_cyr(out.back()));
            if (near) c = cyr[li];
        }
        if (c == U'.' && out.size() >= 2 && out[out.size() - 1] == U'.' && out[out.size() - 2] == U'.') continue;
        out += c;
    }
    return out;
}

// «1) ... 2) ...» -> пункты (номер -> текст); номер — цифра со скобкой после пробела или начала строки
std::map<int, u32string> items(const u32string& t) {
    std::map<int, u32string> out;
    int cur = 0;
    for (size_t i = 0; i < t.size(); i++) {
        if (t[i] >= U'1' && t[i] <= U'9' && i + 1 < t.size() && t[i + 1] == U')' &&
            (i == 0 || t[i - 1] == U' ' || t[i - 1] == U'\n' || t[i - 1] == U'\t')) {
            int n = (int)(t[i] - U'0');
            if (n == cur + 1) { cur = n; i++; continue; }
        }
        if (cur) out[cur] += t[i];
    }
    return out;
}

// убирает подсказки в скобках: «зап..вать (водой)» -> «зап..вать»
u32string drop_parens(const u32string& s) {
    u32string out;
    int depth = 0;
    for (char32_t c : s) {
        if (c == U'(') { depth++; continue; }
        if (c == U')') { if (depth) depth--; continue; }
        if (!depth) out += c;
    }
    return out;
}

vector<u32string> words(const u32string& s) {  // слова из букв, дефиса и «..»
    vector<u32string> out;
    u32string w;
    for (char32_t c : s) {
        if (is_cyr(c) || c == U'.' || c == U'-' || c == U'[' || c == U']') w += c;
        else { if (!w.empty()) out.push_back(w); w.clear(); }
    }
    if (!w.empty()) out.push_back(w);
    for (auto& x : out) {  // точка в конце слова — конец предложения, если это не «..»
        while (!x.empty() && x.back() == U'.' && x.find(U"..") != x.size() - 2) x.pop_back();
        while (!x.empty() && x.front() == U'-') x.erase(0, 1);
    }
    return out;
}

// задание 4: номера пунктов с верно выделенной ударной гласной
string task4(const u32string& t, string& why) {
    auto it = items(t);
    if (it.size() < 3) { why = "не нашёл пунктов 1) 2) 3)"; return ""; }
    string ans;
    bool single = false;
    for (auto& [n, s] : it) {
        u32string w;
        for (auto& x : words(drop_parens(s))) {
            bool up = false;
            for (char32_t c : x) up |= is_upper(c);
            if (up) { w = x; break; }
        }
        if (w.empty()) { why = "пункт " + std::to_string(n) + ": нет слова с прописной"; return ""; }
        string r;
        int v = stress_ok(w, r);
        if (v == -1) { why = "пункт " + std::to_string(n) + " " + encode(w) + ": " + r; return ""; }
        if (v <= -2) { single = true; v = -2 - v; }
        if (v == 1) ans += std::to_string(n);
    }
    if (single) why = "один источник";
    return ans.empty() ? "0" : ans;
}

// слова в скобках: «(травы) колыш..тся» -> {травы}
vector<u32string> words(const u32string& s);
vector<u32string> paren_words(const u32string& s) {
    u32string in;
    int depth = 0;
    for (char32_t c : s) {
        if (c == U'(') { depth++; in += U' '; continue; }
        if (c == U')') { if (depth) depth--; in += U' '; continue; }
        if (depth) in += c;
    }
    return words(in);
}

// задания 9-12: номера рядов, где во всех словах пропущена одна и та же буква.
// Ряд подходит, если у каждого слова одна возможная буква и она общая; не подходит, если общей буквы нет ни при
// каком выборе; иначе — не знаю (выбор зависит от смысла: «отв..рить (дверь)»)
string task_letters(const u32string& t, string& why) {
    auto it = items(t);
    if (it.size() < 3) { why = "не нашёл рядов 1) 2) 3)"; return ""; }
    string ans;
    bool single = false;
    for (auto& [n, row] : it) {
        vector<Fill> fs;
        u32string seg;
        auto flush = [&]() {
            char num = hint_number(paren_words(seg));
            for (auto& w : words(drop_parens(seg))) {
                if (w.find(U"..") == u32string::npos && w.find(U'[') == u32string::npos) continue;
                Fill f = candidates(lower(w));
                by_number(lower(w), num, f.s);
                fs.push_back(f);
            }
            seg.clear();
        };
        for (char32_t c : row) { if (c == U',' || c == U';') flush(); else seg += c; }
        flush();
        if (fs.size() < 2) { why = "ряд " + std::to_string(n) + ": не вижу пропусков"; return ""; }
        std::set<char32_t> common;
        bool first = true, all_one = true, unknown_word = false;
        string w_why;
        for (auto& f : fs) {
            if (f.s.empty()) { unknown_word = true; w_why = f.why; continue; }
            if (f.s.size() > 1) { all_one = false; w_why = f.why; }
            if (first) { common = f.s; first = false; continue; }
            std::set<char32_t> x;
            for (auto c : common) if (f.s.count(c)) x.insert(c);
            common = x;
        }
        if (!first && common.empty()) continue;  // общей буквы нет — ряд не подходит
        if (unknown_word || !all_one) { why = "ряд " + std::to_string(n) + ": " + w_why; return ""; }
        for (auto& f : fs) single |= f.single;
        ans += std::to_string(n);
    }
    if (single) why = "один источник";
    return ans.empty() ? "0" : ans;
}

// ---------- правила 13-15: имена и выключатель ----------
string RULE;
// RUSSKIY_OFF=имя,имя: эти правила отвечают «не знаю». По умолчанию выключены правила задания 14 с точностью
// ниже 98% на половине A банка (rule_stats.py, 27.10): там решает смысл и синтаксис, а не словарь;
// так же выключены слабые правила 13 (недо-, местоимения) и 15 (зависимые слова у полных форм)
std::set<string> OFF = {"п6", "п7", "п8", "п10", "п11", "п12", "п13", "п14", "п15", "п16", "п17", "п18", "п19",
                        "н6", "н12", "нн6", "нн7"};
template <class T> T rule(const char* name, T v) {
    RULE = name;
    if (OFF.count(name)) { if constexpr (std::is_same<T, char>::value) return '?'; else return -1; }
    return v;
}

// ---------- задания 13-15: слова в предложении ----------

// OpenCorpora пишет ё, тексты заданий часто — е: «освещенная» ищем и как «освещённая»
bool in_oc_yo(const u32string& w) {
    if (in_oc(w)) return true;
    u32string lw = lower(w);
    for (size_t i = 0; i < lw.size(); i++)
        if (lw[i] == U'е') { u32string v = lw; v[i] = U'ё'; if (in_oc(v)) return true; }
    return false;
}
int oc_flags_yo(const u32string& w) {
    int f = oc_flags(w);
    if (f >= 0) return f;
    u32string lw = lower(w);
    for (size_t i = 0; i < lw.size(); i++)
        if (lw[i] == U'е') { u32string v = lw; v[i] = U'ё'; f = oc_flags(v); if (f >= 0) return f; }
    return -1;
}
bool both(const u32string& w) { return in_oc_yo(w) && in_hun(w); }
bool any_dict(const u32string& w) { return in_oc_yo(w) || in_hun(w); }
// слово через дефис: Hunspell принимает любые две части через дефис, поэтому — OpenCorpora и RUAccent
bool hyph_both(const u32string& h) { return in_oc_yo(h) && in_acc(h); }
bool hyph_any(const u32string& h) { return in_oc_yo(h) || in_acc(h); }
bool has(int f, int bits) { return f > 0 && (f & bits); }

// выделенное слово из прописных букв и групп в скобках без пробелов: «(НЕ)ОБОЗЛЁН», «ДАВНЫМ(ДАВНО)», «(В)(ПОЛ)СИЛЫ»
struct Compound { vector<u32string> parts; size_t start = 0, end = 0; };

vector<Compound> compounds(const u32string& t) {
    vector<Compound> out;
    for (size_t i = 0; i < t.size();) {
        bool begins = is_upper(t[i]) || (t[i] == U'(' && i + 1 < t.size() && is_upper(t[i + 1]));
        if (!begins || (i && is_cyr(t[i - 1]))) { i++; continue; }
        Compound c;
        c.start = i;
        size_t j = i;
        bool paren = false;
        while (j < t.size()) {
            if (t[j] == U'(') {
                size_t k = t.find(U')', j);
                if (k == u32string::npos) break;
                u32string in = t.substr(j + 1, k - j - 1);
                bool ok = !in.empty();
                for (char32_t ch : in) ok &= is_upper(ch) || ch == U'-';
                if (!ok) break;
                c.parts.push_back(in);
                paren = true;
                j = k + 1;
                // «(ПО) ГРОМЧЕ» — пробел после скобки перед прописным словом
                if (j + 1 < t.size() && t[j] == U' ' && is_upper(t[j + 1])) j++;
            } else if (is_upper(t[j]) || t[j] == U'-') {
                u32string run;
                while (j < t.size() && (is_upper(t[j]) || t[j] == U'-')) run += t[j++];
                if (j < t.size() && is_lower(t[j])) { c.parts.clear(); break; }  // обычное слово с прописной
                c.parts.push_back(run);
            } else break;
        }
        c.end = j;
        if (paren && c.parts.size() >= 2) { out.push_back(c); i = j; }
        else i = std::max(j, i + 1);
    }
    return out;
}

// слова и знаки препинания после позиции: «, а узкий» -> {",", "а", "узкий"}
vector<u32string> tokens_after(const u32string& t, size_t pos, int n) {
    vector<u32string> out;
    size_t i = pos;
    while (i < t.size() && (int)out.size() < n) {
        if (t[i] == U' ' || t[i] == U'\n' || t[i] == U'\t') { i++; continue; }
        if (is_cyr(t[i])) {
            u32string w;
            while (i < t.size() && (is_cyr(t[i]) || t[i] == U'-')) w += t[i++];
            out.push_back(lower(w));
        } else { out.push_back(u32string(1, t[i])); i++; }
    }
    return out;
}

// последние n слов перед позицией (без знаков; знак препинания обрывает)
vector<u32string> words_before(const u32string& t, size_t pos, int n) {
    vector<u32string> out;
    size_t i = pos;
    while (i > 0 && (int)out.size() < n) {
        i--;
        if (t[i] == U' ') continue;
        if (!is_cyr(t[i]) && t[i] != U'-') break;
        size_t e = i + 1;
        while (i > 0 && (is_cyr(t[i - 1]) || t[i - 1] == U'-')) i--;
        out.push_back(lower(t.substr(i, e - i)));
    }
    return out;  // ближайшее — первое
}

bool in_list(const u32string& w, std::initializer_list<const char32_t*> l) {
    for (auto x : l) if (w == x) return true;
    return false;
}

// зависимые слова перед причастием: наречие («давно не глаженые» — через «не»); усилители «очень, совершенно»
// не зависимые
bool dep_before_words(const u32string& t, size_t pos) {
    auto prev = words_before(t, pos, 4);
    size_t i = 0;
    if (i < prev.size() && prev[i] == U"не") i++;
    if (i >= prev.size()) return false;
    static const std::initializer_list<const char32_t*> intens = {U"очень", U"совершенно", U"крайне", U"весьма",
        U"абсолютно", U"вполне", U"почти", U"совсем", U"чрезвычайно", U"достаточно", U"настолько", U"слишком",
        U"так", U"столь", U"довольно", U"особенно", U"исключительно", U"предельно", U"необычайно"};
    int f0 = oc_flags_yo(prev[i]);
    if (has(f0, ADVB) && !has(f0, PREP | CONJ) && !in_list(prev[i], intens)) return true;
    return false;  // предложный оборот перед причастием не признак: «к числу не действующих» (27.10, половина A)
}

// задание 13: 1 — слитно, 0 — раздельно, -1 — не знаю
int ne_together(const u32string& t, const Compound& c, string& why) {
    u32string particle = lower(c.parts[0]);
    u32string w = lower(c.parts.back());
    auto prev = words_before(t, c.start, 2);
    auto next = tokens_after(t, c.end, 3);
    u32string p1 = prev.empty() ? U"" : prev[0];
    u32string n1 = next.empty() ? U"" : next[0], n2 = next.size() > 1 ? next[1] : U"";
    if (particle == U"ни") {
        if (c.parts.size() == 3) return rule("н1", 0);          // ни о ком: частица, предлог, местоимение
        int fw = oc_flags_yo(lower(c.parts.back()));
        if (has(fw, VERB | GRND) && !has(fw, ADJF | NOUN | ADVB | PRTF)) return rule("н2", 0);  // во что бы то ни стало
        why = "НИ"; return -1;
    }
    if (particle != U"не" || c.parts.size() != 2) { why = "не НЕ"; return -1; }
    u32string m = U"не" + w;
    // без НЕ не употребляется: ненавидеть, негодовать, невежда
    if (!any_dict(w) && both(m)) return rule("н3", 1);
    // несмотря на, невзирая на — предлоги
    if ((w == U"смотря" || w == U"взирая") && (n1 == U"на" || n1 == U"ни")) return rule("н4", 1);
    int f = oc_flags_yo(w);
    if (f < 0) { why = encode(w) + ": нет в словаре"; return -1; }
    if (w == U"хотя") return rule("н20", 1);  // нехотя («хотя» в словаре ещё и деепричастие от «хотеть»)
    // не что иное, как; не кто иной, как — раздельно
    if ((w == U"что" || w == U"кто") && (n1 == U"иное" || n1 == U"иной" || n1 == U"другое" || n1 == U"другой"))
        return rule("н18", 0);
    if (in_list(w, {U"даром", U"когда", U"где", U"куда", U"мало", U"много", U"раз", U"зачем"})) {
        why = encode(w) + ": по смыслу (недаром / не даром)"; return -1;
    }
    // противопоставление с «а» в ближайших словах: не когда он идёт к Вязникам, а когда...
    auto far = tokens_after(t, c.end, 7);
    for (size_t i = 0; i + 1 < far.size(); i++)
        if (far[i] == U"," && far[i + 1] == U"а" && !has(f, VERB | GRND)) return rule("н5", 0);
    bool verbal = has(f, VERB | GRND) && !has(f, ADJF | ADJS | NOUN | ADVB | PRTF | PRTS);
    // «(НЕ)ИСТОЩИМ на выдумки» — краткое прилагательное «неистощим», а не глагол «истощим»
    if (verbal && both(m) && has(oc_flags_yo(m), ADJS | ADJF) && !has(oc_flags_yo(m), VERB | GRND))
        return rule("н19", 1);
    if (verbal) {
        if (any_dict(m) && has(oc_flags_yo(m), VERB | GRND)) {
            // недо-: «не досмотрел до конца» (не закончил) — раздельно; «недоставало», «недоедал» — слитно
            if (w.substr(0, 2) != U"до") { why = encode(m) + " — тоже глагол"; return -1; }
            return rule("н6", n1 == U"до" ? 0 : 1);
        }
        return rule("н7", 0);
    }
    // усилители и противопоставление: далеко не, вовсе не, отнюдь не; не широкий, а узкий
    if (in_list(p1, {U"далеко", U"вовсе", U"отнюдь", U"ничуть", U"нисколько", U"ничем", U"никому", U"никем",
                     U"никогда", U"нисколечко", U"ничего"})) return rule("н8", 0);
    if (n1 == U"," && n2 == U"а") return rule("н9", 0);
    if (n1 == U"а") return rule("н10", 0);
    if (has(f, COMP) && !has(f, ADJF | NOUN)) return rule("н11", 0);  // не лучше
    if (has(f, NPRO | NUMR) && !has(f, ADJF | NOUN | ADVB)) return rule("н12", 0);
    if (has(f, PRTS) && !has(f, ADJS | ADJF | NOUN | ADVB)) return rule("н13", 0);  // краткое причастие: не обозлён
    if (has(f, PRTF)) {
        // причастие: с зависимыми словами — раздельно, без — слитно
        bool dep_before = dep_before_words(t, c.start);
        int fn = oc_flags_yo(n1);
        bool own_ablt = has(f, ABLT);  // само причастие в творительном — следующее слово в творительном согласовано
        bool dep_after = has(fn, PREP) ||
            (!own_ablt && has(fn, ABLT) && has(fn, NOUN | NPRO) && !has(fn, NOM_SG | NOM_PL | ACCS));
        if (dep_before || dep_after) return rule("н14", 0);
        if (n1 == U"," || n1 == U"—" || n1 == U"–") { why = encode(w) + ": причастие, после запятой может быть зависимое"; return -1; }
        if (has(fn, NOUN) && !has(fn, ABLT | PREP)) return rule("н15", both(m) ? 1 : -1);
        if (!has(f, ADJF | NOUN)) { why = encode(w) + ": причастие, зависимые слова неясны"; return -1; }
    }
    if (has(f, ADJF | ADJS | NOUN | ADVB)) {
        if (both(m)) return rule("н16", 1);                 // неширокий, неровности, незадолго
        if (!any_dict(m)) return rule("н17", 0);            // не всегда, не очень
        why = encode(m) + ": только в одном словаре"; return -1;
    }
    why = encode(w) + ": часть речи"; return -1;
}

string task13(const u32string& t, string& why) {
    size_t first = t.find(U"1)");
    u32string head = first == u32string::npos ? t : t.substr(0, first);
    bool want_apart = head.find(U"РАЗДЕЛЬНО") != u32string::npos;
    bool want_together = head.find(U"СЛИТНО") != u32string::npos;
    if (want_apart == want_together) { why = "не понял, слитно или раздельно"; return ""; }
    auto it = items(t);
    if (it.size() < 3) { why = "не нашёл пунктов"; return ""; }
    string ans;
    for (auto& [n, s] : it) {
        auto cs = compounds(s);
        if (cs.size() != 1) { why = "пункт " + std::to_string(n) + ": выделенных слов " + std::to_string(cs.size()); return ""; }
        string r;
        int v = ne_together(s, cs[0], r);
        if (v < 0) { why = "пункт " + std::to_string(n) + ": " + r; return ""; }
        if ((v == 1) == want_together) ans += std::to_string(n);
    }
    return ans.empty() ? "0" : ans;
}

// задание 14: 'S' слитно, 'D' дефис, 'R' раздельно, '?' не знаю
char spelling(const u32string& t, const Compound& c, string& why) {
    vector<u32string> p;
    for (auto& x : c.parts) p.push_back(lower(x));
    auto next = tokens_after(t, c.end, 3);
    u32string n1 = next.empty() ? U"" : next[0], n2 = next.size() > 1 ? next[1] : U"";
    u32string all;
    for (auto& x : p) all += x;
    if (p.size() == 3) { if (both(all)) return rule("п1", 'S'); why = encode(all); return '?'; }
    if (p.size() != 2) { why = "частей " + std::to_string(p.size()); return '?'; }
    u32string x = p[0], y = p[1], m = x + y, h = x + U"-" + y;
    // пол- : пол-яблока, пол-лимона — дефис; полдня — слитно
    if (x == U"пол") {
        if (!has(oc_flags(y), NOUN)) { why = "пол + не существительное"; return '?'; }
        return rule("п2", (is_vowel(y[0]) || y[0] == U'л') ? 'D' : 'S');
    }
    bool inM = both(m), inH = hyph_both(h), anyM = any_dict(m), anyH = hyph_any(h);
    if (inH && !anyM) {
        // по-зимнему, но «по зимнему парку»
        if (x == U"по" && has(oc_flags(n1), NOUN) && has(oc_flags(n1), DATV)) return rule("п3", 'R');
        return rule("п4", 'D');
    }
    if (!anyM && !anyH) {  // в течение, по мнению, так как — первая часть служебная
        if (has(oc_flags_yo(x), PREP | CONJ | PRCL) && !has(oc_flags_yo(x), ADVB | ADJF)) return rule("п5", 'R');
        why = encode(m) + ": нет в словарях"; return '?';
    }
    if (inM && !anyH) {
        if (m == U"также" || m == U"тоже") {
            if (n1 == U"," && n2 == U"как") return rule("п6", 'R');
            if (n1 == U"как" || n1 == U"самое" || n1 == U"что" || (n1 == U"," && n2 == U"что")) return rule("п7", 'R');
            return rule("п8", 'S');
        }
        if (m == U"чтобы" || m == U"что-бы") { why = "что(бы) — по смыслу"; return '?'; }
        auto prev = words_before(t, c.start, 1);
        u32string p1 = prev.empty() ? U"" : prev[0];
        if (m == U"ввиду" && p1.size() >= 3 && p1.substr(0, 3) == U"име") return rule("п9", 'R');  // иметь в виду
        if (x == U"за" || x == U"с") {
            if (n1 == U"," && (n2 == U"что" || n2 == U"чтобы")) return rule("п10", 'R');
            if (n1 == U"что" || n1 == U"чтобы") return rule("п11", 'R');
        }
        int fm = oc_flags_yo(m);
        if (has(fm, CONJ) && !has(fm, NOUN | ADJF | NPRO)) {  // поскольку, притом, причём, зато
            if ((x == U"за" || x == U"при") && (n1 == U"что" || (n1 == U"," && n2 == U"что"))) return rule("п12", 'R');
            return rule("п13", 'S');
        }
        bool prep = in_list(x, {U"в", U"во", U"с", U"со", U"на", U"до", U"по", U"от", U"из", U"за", U"без", U"под",
                               U"над", U"к", U"у", U"при", U"через"});
        int fn0 = oc_flags_yo(n1);
        bool func_next = n1.size() <= 3 && has(fn0, CONJ | PRCL | PREP);  // «и», «не», «по» — не зависимое слово
        if (!prep) {  // тот(час): за наречием — глагол или знак
            if (has(fm, ADVB) && (n1.size() == 1 || func_next || has(fn0, VERB | GRND | PRTS | ADVB))) return rule("п14", 'S');
            why = encode(m) + ": не предлог"; return '?';
        }
        if (has(fm, PREP)) {  // производный предлог: вследствие, ввиду, насчёт, навстречу
            if (y.size() > 2 && y.substr(y.size() - 2) == U"ии") return rule("п15", 'R');  // в следствии
            return rule("п16", 'S');
        }
        int fn = oc_flags_yo(n1);
        if (func_next) return rule("п17", 'S');
        if (has(fn, NOUN | ADJF | PRTF | NPRO) && has(fn, GENT)) return rule("п18", 'R');  // от того берега, с начала года
        if (n1.size() == 1 || has(fn, VERB | PRTS | ADVB | PRCL | CONJ | GRND | PRED)) return rule("п19", 'S');
        why = encode(m) + ": по следующему слову неясно"; return '?';
    }
    why = encode(m) + "/" + encode(h) + ": словари"; return '?';
}

string task14(const u32string& t, string& why) {
    size_t first = t.find(U"1)");
    u32string head = first == u32string::npos ? t : t.substr(0, first);
    char want = head.find(U"ДЕФИС") != u32string::npos ? 'D' :
                head.find(U"РАЗДЕЛЬНО") != u32string::npos ? 'R' :
                head.find(U"СЛИТНО") != u32string::npos ? 'S' : 0;
    if (!want) { why = "не понял, как надо писать"; return ""; }
    auto it = items(t);
    if (it.size() < 3) { why = "не нашёл пунктов"; return ""; }
    string ans;
    for (auto& [n, s] : it) {
        auto cs = compounds(s);
        if (cs.empty()) { why = "пункт " + std::to_string(n) + ": нет выделенных слов"; return ""; }
        bool no = false, unknown = false;
        string r;
        for (auto& c : cs) {
            string rr;
            char v = spelling(s, c, rr);
            if (v == '?') { unknown = true; r = rr; } else if (v != want) no = true;
        }
        if (no) continue;
        if (unknown) { why = "пункт " + std::to_string(n) + ": " + r; return ""; }
        ans += std::to_string(n);
    }
    return ans.empty() ? "0" : ans;
}

// задание 15: 1 — НН, 0 — Н, -1 — не знаю
int nn(const u32string& t, size_t a, size_t b, const u32string& word, size_t mk, size_t mk_end, string& why) {
    u32string head = lower(word.substr(0, mk)), tail = lower(word.substr(mk_end));
    u32string wN = head + U"н" + tail, wNN = head + U"нн" + tail;
    bool bN = both(wN), bNN = both(wNN), aN = any_dict(wN), aNN = any_dict(wNN);
    if (bN && !aNN) return rule("нн1", 0);
    if (bNN && !aN) return rule("нн2", 1);
    if (!aN && !aNN) {
        bool cN = in_acc(wN), cNN = in_acc(wNN);
        if (cN != cNN) { why = "один источник"; return rule("нн3", cNN ? 1 : 0); }
        why = encode(wN) + "/" + encode(wNN) + ": нет в словарях"; return -1;
    }
    if (!(aN && aNN)) { why = encode(wN) + "/" + encode(wNN) + ": словари расходятся"; return -1; }
    // оба есть: кованый / кованный, связано / связанно
    int fN = oc_flags_yo(wN), fNN = oc_flags_yo(wNN);
    auto next = tokens_after(t, b, 2);
    auto prev = words_before(t, a, 1);
    int fn = next.empty() ? 0 : oc_flags_yo(next[0]);
    int fp = prev.empty() ? 0 : oc_flags_yo(prev[0]);
    bool own_ablt = has(fN, ABLT) || has(fNN, ABLT);  // «кова(2)ыми решётками» — решётками согласовано, не зависимое
    bool dep_after = has(fn, PREP) ||
        (!own_ablt && has(fn, ABLT) && has(fn, NOUN | NPRO) && !has(fn, NOM_SG | NOM_PL));
    bool dep_before = dep_before_words(t, a) ||
        (has(fp, ABLT) && has(fp, NOUN | NPRO) && !has(fp, NOM_SG | NOM_PL));
    // «чита(3)ой им книгой» — местоимение в творительном (им, ими, мной...) всегда зависимое
    if (!next.empty() && has(fn, NPRO) && has(fn, ABLT) && !has(fn, NOUN)) dep_after = true;
    // наречие на -о перед глаголом: «сдержа(1)о посовещались», «смущё(2)о улыбнулась» — как прилагательное (НН)
    if (has(fNN, ADVB) && !next.empty() && (has(fn, VERB | GRND) || next[0] == U"не")) return rule("нн4", 1);
    if (has(fN, PRTS) && has(fNN, ADJS | ADVB)) {  // краткое причастие (Н) или краткое прилагательное (НН)
        if (dep_after) return rule("нн5", 0);
        why = encode(wN) + "/" + encode(wNN) + ": краткая форма"; return -1;
    }
    if (has(fNN, PRTF) && has(fN, ADJF)) {  // полное: с зависимыми словами — причастие (НН), без — прилагательное (Н)
        if (dep_after || dep_before) return rule("нн6", 1);
        if (!next.empty() && has(fn, NOUN) && !dep_before) return rule("нн7", 0);
    }
    why = encode(wN) + "/" + encode(wNN) + ": оба слова есть"; return -1;
}

string task15(const u32string& t, string& why) {
    size_t first = t.find(U"(1)");
    if (first == u32string::npos) { why = "нет (1)"; return ""; }
    u32string head = t.substr(0, first);
    // «пишется НН» / «пишется одна буква Н» / «пишется Н»
    size_t q = head.find(U"пишется");
    u32string after = q == u32string::npos ? head : head.substr(q);
    bool want_nn = after.find(U"НН") != u32string::npos;
    string ans;
    for (int k = 1; k <= 9; k++) {
        u32string mark = U"(" + u32string(1, U'0' + k) + U")";
        size_t m = t.find(mark);
        if (m == u32string::npos) break;
        size_t a = m, b = m + mark.size();
        while (a > 0 && (is_cyr(t[a - 1]) || t[a - 1] == U'-')) a--;
        while (b < t.size() && (is_cyr(t[b]) || t[b] == U'-')) b++;
        if (a == m && b == m + mark.size()) { why = "(" + std::to_string(k) + ") не в слове"; return ""; }
        u32string word = t.substr(a, b - a);
        size_t mk = m - a;
        // «подли (4)ом» — пробел внутри слова
        if (a == m && a >= 2 && t[a - 1] == U' ' && is_cyr(t[a - 2])) {
            size_t a2 = a - 1;
            while (a2 > 0 && is_cyr(t[a2 - 1])) a2--;
            word = t.substr(a2, a - 1 - a2) + t.substr(m, b - m);
            mk = a - 1 - a2;
            a = a2;
        }
        string r;
        int v = nn(t, a, b, word, mk, mk + mark.size(), r);
        if (v < 0) { why = "(" + std::to_string(k) + ") " + r; return ""; }
        if ((v == 1) == want_nn) ans += std::to_string(k);
    }
    return ans.empty() ? "0" : ans;
}

// ---------- команды ----------

// аргументы в кавычках («», "") или числа, через запятую
vector<u32string> args(const u32string& s) {
    vector<u32string> out;
    size_t i = 0;
    while (i < s.size()) {
        while (i < s.size() && (s[i] == U' ' || s[i] == U',')) i++;
        if (i >= s.size()) break;
        if (s[i] == U'"' || s[i] == U'«') {
            char32_t close = s[i] == U'"' ? U'"' : U'»';
            size_t j = s.rfind(close);  // текст задания может содержать кавычки: берём до последней
            if (out.size() == 0 && s.find(U',') != u32string::npos) {
                // первый аргумент — до закрывающей кавычки перед запятой
                size_t k = s.find(close, i + 1);
                if (k != u32string::npos) j = k;
            }
            if (j == u32string::npos || j <= i) j = s.size();
            out.push_back(s.substr(i + 1, j - i - 1));
            i = j + 1;
        } else {
            size_t j = s.find(U',', i);
            if (j == u32string::npos) j = s.size();
            u32string a = s.substr(i, j - i);
            while (!a.empty() && a.back() == U' ') a.pop_back();
            out.push_back(a);
            i = j;
        }
    }
    return out;
}

string run(const u32string& line) {
    size_t p = line.find(U'('), q = line.rfind(U')');
    if (p == u32string::npos || q == u32string::npos || q < p) return "ошибка: нужна команда(аргументы)";
    u32string name = line.substr(0, p);
    while (!name.empty() && name.back() == U' ') name.pop_back();
    u32string body = clean(line.substr(p + 1, q - p - 1));
    string why;
    if (name == U"ЕСТЬ") {
        auto a = args(body);
        if (a.empty()) return "ошибка: нет слова";
        u32string w = a[0];
        auto st = acc_stress(w);
        return string("OpenCorpora: ") + (in_oc(w) ? "да" : "нет") + "; Hunspell: " + (in_hun(w) ? "да" : "нет") +
               "; RUAccent: " + (st.empty() ? "нет" : "да");
    }
    if (name == U"УДАРЕНИЕ") {
        auto a = args(body);
        if (a.empty()) return "ошибка: нет слова";
        int v = stress_ok(a[0], why);
        if (v == 1) return "верно";
        if (v == 0) return "неверно";
        if (v <= -2) return string(v == -3 ? "верно" : "неверно") + " (" + why + ")";
        return "не знаю: " + why;
    }
    if (name == U"БУКВА") {
        auto a = args(body);
        if (a.empty()) return "ошибка: нет слова";
        char32_t c = letter(lower(a[0]), why);
        if (c == U'?') return "не знаю: " + why;
        return c ? encode(u32string(1, c)) : "∅";
    }
    if (name == U"РАЗБОР") {  // по пунктам: решение и правило (для замера точности каждого правила)
        size_t comma = body.find(U',');
        int n = std::atoi(encode(body.substr(0, comma)).c_str());
        u32string text = body.substr(comma + 1);
        string out;
        if (n == 13 || n == 14) {
            for (auto& [k, it] : items(text)) {
                for (auto& c : compounds(it)) {
                    string r;
                    RULE = "";
                    string v = n == 13 ? std::to_string(ne_together(it, c, r)) : string(1, spelling(it, c, r));
                    out += std::to_string(k) + ":" + v + ":" + (RULE.empty() ? "-" : RULE) + "; ";
                }
            }
        } else if (n == 15) {
            for (int k = 1; k <= 9; k++) {
                u32string mark = U"(" + u32string(1, U'0' + k) + U")";
                size_t m = text.find(mark);
                if (m == u32string::npos) break;
                size_t a = m, b = m + mark.size();
                while (a > 0 && (is_cyr(text[a - 1]) || text[a - 1] == U'-')) a--;
                while (b < text.size() && (is_cyr(text[b]) || text[b] == U'-')) b++;
                string r;
                RULE = "";
                int v = nn(text, a, b, text.substr(a, b - a), m - a, m - a + mark.size(), r);
                out += std::to_string(k) + ":" + std::to_string(v) + ":" + (RULE.empty() ? "-" : RULE) + "; ";
            }
        }
        return out;
    }
    if (name == U"НАПИСАНИЕ") {  // отладка задания 14: решение по каждому выделенному слову
        string out;
        for (auto& c : compounds(body)) {
            string r;
            char v = spelling(body, c, r);
            u32string all;
            for (auto& p : c.parts) all += U"(" + p + U")";
            out += encode(all) + ":" + string(1, v) + (r.empty() ? "" : " [" + r + "]") + "; ";
        }
        return out;
    }
    if (name == U"ЗАДАНИЕ") {
        size_t comma = body.find(U',');
        if (comma == u32string::npos) return "ошибка: ЗАДАНИЕ(номер, \"текст\")";
        int n = std::atoi(encode(body.substr(0, comma)).c_str());
        u32string text = body.substr(comma + 1);
        while (!text.empty() && (text[0] == U' ' || text[0] == U'"' || text[0] == U'«')) text.erase(0, 1);
        while (!text.empty() && (text.back() == U' ' || text.back() == U'"' || text.back() == U'»')) text.pop_back();
        string ans;
        if (n == 4) ans = task4(text, why);
        else if (n >= 9 && n <= 12) ans = task_letters(text, why);
        else if ((n == 13 || n == 14) && !std::getenv("RUSSKIY_ALL"))
            // отложены 27.10 после двух попыток: на нетронутой половине банка 13 — 7/10, 14 — без ответов; решают
            // смысл и синтаксис (недаром / не даром, оттого / от того берега). RUSSKIY_ALL=1 — включить для опытов
            return "не знаю: задание " + std::to_string(n) + " орган пока не решает (отложено)";
        else if (n == 13) ans = task13(text, why);
        else if (n == 14) ans = task14(text, why);
        else if (n == 15) ans = task15(text, why);
        else return "не знаю: задание " + std::to_string(n) + " орган не решает";
        if (ans.empty()) return "не знаю: " + why;
        return why.empty() ? ans : ans + " (" + why + ")";
    }
    return "ошибка: неизвестная команда";
}

int main(int argc, char** argv) {
    if (argc > 1) DATA = argv[1];
    else {  // по умолчанию — data рядом с программой
        string self = argv[0];
        size_t s = self.find_last_of("/\\");
        DATA = (s == string::npos ? string(".") : self.substr(0, s)) + "/data";
    }
    if (!load_all()) return 1;
    if (const char* off = std::getenv("RUSSKIY_OFF")) {
        OFF.clear();
        string o = off, cur;
        for (char ch : o + ",") { if (ch == ',') { if (!cur.empty()) OFF.insert(cur); cur.clear(); } else cur += ch; }
    }
    std::ios::sync_with_stdio(false);
    string line;
    while (std::getline(std::cin, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;
        std::cout << line << " = " << run(decode(line)) << "\n" << std::flush;
    }
    return 0;
}
