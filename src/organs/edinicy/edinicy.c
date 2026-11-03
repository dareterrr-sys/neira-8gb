/* Переводчик единиц — «орган» Нейры: всё к СИ (метр, килограмм, секунда, ампер, кельвин, моль, кандела).
 *
 * Модель путается в переводах (км/ч в м/с, футы, галлоны, градусы Фаренгейта) так же, как в счёте: это
 * перевод условия в числа, а не мысль. Мозг только пишет команду, точный ответ считает код.
 *
 * Вход: по одной команде в строке:
 *     СИ(72 км/ч)                  -> 20 м/с
 *     ПЕРЕВЕСТИ(3 часа, мин)       -> 180 мин
 *     ПЕРЕВЕСТИ(100 °F, °C)        -> 37.78 °C
 * Выход: «команда = ответ» или «команда = ошибка: ...».
 *
 * Единицы: длина (мм, см, м, км, дюйм, фут, ярд, миля, морская миля, верста...), масса (мг, г, кг, т, ц, фунт,
 * унция, пуд, карат), время (мс, с, мин, ч, сутки, неделя, год = 365 суток), площадь (га, сотка, акр), объём (мл, л,
 * галлон США, баррель), сила (Н, кгс), энергия (Дж, кал, ккал, эВ), мощность (Вт, л.с.), давление (Па, атм, бар,
 * мм рт. ст., psi), ток и заряд (А, Кл), напряжение (В), сопротивление (Ом), частота (Гц), температура (К, °C, °F),
 * скорость (узел). Приставки СИ к символам (кВт, МПа, мкс, нм...). Составные: км/ч, кВт*ч, кг*м/с2, Дж/(кг*К),
 * степени: м2, м^2, м². Сложить или перевести разные величины (км в кг) нельзя — это ошибка в задаче.
 *
 * Сборка: gcc -O2 -std=c99 -static -o edinicy.exe edinicy.c -lm
 */
#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ND 7   /* измерения: м, кг, с, А, К, моль, кд */
static const char *DIM_NAME[ND] = {"м", "кг", "с", "А", "К", "моль", "кд"};

typedef struct {
    double f;        /* множитель к СИ */
    double off;      /* сдвиг (только температура: СИ = v*f + off) */
    int d[ND];
} Q;

typedef struct {
    const char *name;
    double f, off;
    int d[ND];
} Unit;

#define L  {1,0,0,0,0,0,0}
#define M  {0,1,0,0,0,0,0}
#define T  {0,0,1,0,0,0,0}
#define AR {2,0,0,0,0,0,0}
#define V3 {3,0,0,0,0,0,0}
#define FN {1,1,-2,0,0,0,0}
#define EN {2,1,-2,0,0,0,0}
#define PW {2,1,-3,0,0,0,0}
#define PR {-1,1,-2,0,0,0,0}
#define SP {1,0,-1,0,0,0,0}
#define CU {0,0,0,1,0,0,0}
#define TK {0,0,0,0,1,0,0}

static const Unit UNITS[] = {
    /* длина */
    {"м", 1, 0, L}, {"метр", 1, 0, L}, {"метра", 1, 0, L}, {"метров", 1, 0, L}, {"m", 1, 0, L},
    {"км", 1e3, 0, L}, {"километр", 1e3, 0, L}, {"километра", 1e3, 0, L}, {"километров", 1e3, 0, L}, {"km", 1e3, 0, L},
    {"см", 1e-2, 0, L}, {"сантиметр", 1e-2, 0, L}, {"сантиметра", 1e-2, 0, L}, {"сантиметров", 1e-2, 0, L}, {"cm", 1e-2, 0, L},
    {"мм", 1e-3, 0, L}, {"миллиметр", 1e-3, 0, L}, {"миллиметра", 1e-3, 0, L}, {"миллиметров", 1e-3, 0, L}, {"mm", 1e-3, 0, L},
    {"дм", 0.1, 0, L}, {"дециметр", 0.1, 0, L}, {"дециметра", 0.1, 0, L}, {"дециметров", 0.1, 0, L},
    {"мкм", 1e-6, 0, L}, {"микрон", 1e-6, 0, L}, {"нм", 1e-9, 0, L},
    {"дюйм", 0.0254, 0, L}, {"дюйма", 0.0254, 0, L}, {"дюймов", 0.0254, 0, L}, {"in", 0.0254, 0, L},
    {"фут", 0.3048, 0, L}, {"фута", 0.3048, 0, L}, {"футов", 0.3048, 0, L}, {"ft", 0.3048, 0, L},
    {"ярд", 0.9144, 0, L}, {"ярда", 0.9144, 0, L}, {"ярдов", 0.9144, 0, L}, {"yd", 0.9144, 0, L},
    {"миля", 1609.344, 0, L}, {"мили", 1609.344, 0, L}, {"миль", 1609.344, 0, L}, {"mi", 1609.344, 0, L},
    {"морская миля", 1852, 0, L}, {"морские мили", 1852, 0, L}, {"морских миль", 1852, 0, L},
    {"верста", 1066.8, 0, L}, {"версты", 1066.8, 0, L}, {"вёрст", 1066.8, 0, L}, {"верст", 1066.8, 0, L},
    {"сажень", 2.1336, 0, L}, {"аршин", 0.7112, 0, L}, {"а.е.", 1.495978707e11, 0, L},
    {"световой год", 9.4607304725808e15, 0, L},
    /* масса */
    {"кг", 1, 0, M}, {"килограмм", 1, 0, M}, {"килограмма", 1, 0, M}, {"килограммов", 1, 0, M}, {"kg", 1, 0, M},
    {"г", 1e-3, 0, M}, {"грамм", 1e-3, 0, M}, {"грамма", 1e-3, 0, M}, {"граммов", 1e-3, 0, M}, {"g", 1e-3, 0, M},
    {"мг", 1e-6, 0, M}, {"миллиграмм", 1e-6, 0, M},
    {"т", 1e3, 0, M}, {"тонна", 1e3, 0, M}, {"тонны", 1e3, 0, M}, {"тонн", 1e3, 0, M}, {"t", 1e3, 0, M},
    {"ц", 100, 0, M}, {"центнер", 100, 0, M}, {"центнера", 100, 0, M}, {"центнеров", 100, 0, M},
    {"фунт", 0.45359237, 0, M}, {"фунта", 0.45359237, 0, M}, {"фунтов", 0.45359237, 0, M}, {"lb", 0.45359237, 0, M},
    {"унция", 0.028349523125, 0, M}, {"унции", 0.028349523125, 0, M}, {"унций", 0.028349523125, 0, M},
    {"oz", 0.028349523125, 0, M}, {"пуд", 16.3807, 0, M}, {"пуда", 16.3807, 0, M}, {"пудов", 16.3807, 0, M},
    {"карат", 2e-4, 0, M},
    /* время */
    {"с", 1, 0, T}, {"сек", 1, 0, T}, {"секунда", 1, 0, T}, {"секунды", 1, 0, T}, {"секунд", 1, 0, T}, {"s", 1, 0, T},
    {"мс", 1e-3, 0, T}, {"мин", 60, 0, T}, {"минута", 60, 0, T}, {"минуты", 60, 0, T}, {"минут", 60, 0, T},
    {"min", 60, 0, T}, {"ч", 3600, 0, T}, {"час", 3600, 0, T}, {"часа", 3600, 0, T}, {"часов", 3600, 0, T},
    {"h", 3600, 0, T}, {"сут", 86400, 0, T}, {"сутки", 86400, 0, T}, {"суток", 86400, 0, T},
    {"день", 86400, 0, T}, {"дня", 86400, 0, T}, {"дней", 86400, 0, T},
    {"нед", 604800, 0, T}, {"неделя", 604800, 0, T}, {"недели", 604800, 0, T}, {"недель", 604800, 0, T},
    {"год", 31536000, 0, T}, {"года", 31536000, 0, T}, {"лет", 31536000, 0, T},
    /* площадь, объём */
    {"га", 1e4, 0, AR}, {"гектар", 1e4, 0, AR}, {"гектара", 1e4, 0, AR}, {"гектаров", 1e4, 0, AR},
    {"сотка", 100, 0, AR}, {"сотки", 100, 0, AR}, {"соток", 100, 0, AR}, {"ар", 100, 0, AR},
    {"акр", 4046.8564224, 0, AR}, {"акра", 4046.8564224, 0, AR}, {"акров", 4046.8564224, 0, AR},
    {"л", 1e-3, 0, V3}, {"литр", 1e-3, 0, V3}, {"литра", 1e-3, 0, V3}, {"литров", 1e-3, 0, V3}, {"l", 1e-3, 0, V3},
    {"мл", 1e-6, 0, V3}, {"миллилитр", 1e-6, 0, V3}, {"миллилитров", 1e-6, 0, V3},
    {"галлон", 3.785411784e-3, 0, V3}, {"галлона", 3.785411784e-3, 0, V3}, {"галлонов", 3.785411784e-3, 0, V3},
    {"gal", 3.785411784e-3, 0, V3}, {"баррель", 0.158987294928, 0, V3}, {"баррелей", 0.158987294928, 0, V3},
    /* механика, электричество */
    {"Н", 1, 0, FN}, {"ньютон", 1, 0, FN}, {"кгс", 9.80665, 0, FN},
    {"Дж", 1, 0, EN}, {"джоуль", 1, 0, EN}, {"кал", 4.1868, 0, EN}, {"калория", 4.1868, 0, EN},
    {"ккал", 4186.8, 0, EN}, {"эВ", 1.602176634e-19, 0, EN},
    {"Вт", 1, 0, PW}, {"ватт", 1, 0, PW}, {"л.с.", 735.49875, 0, PW},
    {"Па", 1, 0, PR}, {"паскаль", 1, 0, PR}, {"атм", 101325, 0, PR}, {"бар", 1e5, 0, PR},
    {"мм рт. ст.", 133.322387415, 0, PR}, {"мм рт.ст.", 133.322387415, 0, PR}, {"psi", 6894.757293168, 0, PR},
    {"узел", 1852.0 / 3600, 0, SP}, {"узла", 1852.0 / 3600, 0, SP}, {"узлов", 1852.0 / 3600, 0, SP},
    {"А", 1, 0, CU}, {"ампер", 1, 0, CU}, {"Кл", 1, 0, {0,0,1,1,0,0,0}},
    {"В", 1, 0, {2,1,-3,-1,0,0,0}}, {"вольт", 1, 0, {2,1,-3,-1,0,0,0}}, {"Ом", 1, 0, {2,1,-3,-2,0,0,0}},
    {"Гц", 1, 0, {0,0,-1,0,0,0,0}}, {"моль", 1, 0, {0,0,0,0,0,1,0}}, {"кд", 1, 0, {0,0,0,0,0,0,1}},
    /* температура: шкалы со сдвигом */
    {"К", 1, 0, TK}, {"K", 1, 0, TK}, {"кельвин", 1, 0, TK},
    {"°C", 1, 273.15, TK}, {"°С", 1, 273.15, TK}, {"градус Цельсия", 1, 273.15, TK},
    {"градуса Цельсия", 1, 273.15, TK}, {"градусов Цельсия", 1, 273.15, TK},
    {"°F", 5.0 / 9, 273.15 - 32 * 5.0 / 9, TK}, {"градус Фаренгейта", 5.0 / 9, 273.15 - 32 * 5.0 / 9, TK},
    {"градусов Фаренгейта", 5.0 / 9, 273.15 - 32 * 5.0 / 9, TK},
};
#define NUNITS (sizeof UNITS / sizeof UNITS[0])

/* приставки СИ (длинные раньше: «мк» раньше «м») и единицы, к которым они прибавляются */
static const struct { const char *p; double f; } PREFIX[] = {
    {"мк", 1e-6}, {"Г", 1e9}, {"М", 1e6}, {"к", 1e3}, {"г", 1e2}, {"д", 1e-1}, {"с", 1e-2}, {"м", 1e-3}, {"н", 1e-9},
};
static const char *PREFIXABLE[] = {"м", "г", "с", "л", "Па", "Дж", "Вт", "Н", "В", "А", "Гц", "Ом", "Кл", "моль"};

static char err[400];

static int unit_exact(const char *s, Q *q) {
    for (size_t i = 0; i < NUNITS; ++i)
        if (strcmp(s, UNITS[i].name) == 0) {
            q->f = UNITS[i].f; q->off = UNITS[i].off;
            memcpy(q->d, UNITS[i].d, sizeof q->d);
            return 1;
        }
    return 0;
}

static int unit_token(const char *s, Q *q) {
    if (unit_exact(s, q)) return 1;
    for (size_t i = 0; i < sizeof PREFIX / sizeof PREFIX[0]; ++i) {
        size_t n = strlen(PREFIX[i].p);
        if (strncmp(s, PREFIX[i].p, n) != 0) continue;
        for (size_t j = 0; j < sizeof PREFIXABLE / sizeof PREFIXABLE[0]; ++j)
            if (strcmp(s + n, PREFIXABLE[j]) == 0 && unit_exact(s + n, q)) {
                q->f *= PREFIX[i].f;
                return 1;
            }
    }
    return 0;
}

static void q_mul(Q *a, const Q *b, int power) {
    a->f *= pow(b->f, power);
    for (int i = 0; i < ND; ++i) a->d[i] += power * b->d[i];
}

/* разбор составной единицы: множители через * · ×, деление /, скобки после /, степени 2 ^2 ² ³ */
static const char *p;

static void skip_spaces(void) { while (*p == ' ') ++p; }

static int parse_product(Q *q, int sign);

static int parse_factor(Q *q, int sign) {
    skip_spaces();
    if (*p == '(') {
        ++p;
        if (!parse_product(q, sign)) return 0;
        skip_spaces();
        if (*p != ')') { snprintf(err, sizeof err, "нет закрывающей скобки"); return 0; }
        ++p;
        return 1;
    }
    char tok[64];
    size_t n = 0;
    while (*p && *p != '*' && *p != '/' && *p != '(' && *p != ')' && *p != '^' && *p != ' '
           && !(isdigit((unsigned char)*p)) && strncmp(p, "·", 2) != 0 && strncmp(p, "×", 2) != 0
           && strncmp(p, "²", 2) != 0 && strncmp(p, "³", 2) != 0) {
        if (n + 1 < sizeof tok) tok[n++] = *p;
        ++p;
    }
    tok[n] = 0;
    if (n == 0) { snprintf(err, sizeof err, "пустая единица"); return 0; }
    int power = 1;
    if (*p == '^') ++p;
    if (isdigit((unsigned char)*p)) power = *p++ - '0';
    else if (strncmp(p, "²", 2) == 0) { power = 2; p += 2; }
    else if (strncmp(p, "³", 2) == 0) { power = 3; p += 2; }
    Q u;
    if (!unit_token(tok, &u)) { snprintf(err, sizeof err, "неизвестная единица «%s»", tok); return 0; }
    if (u.off != 0) { snprintf(err, sizeof err, "шкала температуры «%s» не входит в составные единицы", tok); return 0; }
    q_mul(q, &u, sign * power);
    return 1;
}

static int parse_product(Q *q, int sign) {
    if (!parse_factor(q, sign)) return 0;
    for (;;) {
        skip_spaces();
        if (*p == '*') { ++p; if (!parse_factor(q, sign)) return 0; }
        else if (strncmp(p, "·", 2) == 0 || strncmp(p, "×", 2) == 0) { p += 2; if (!parse_factor(q, sign)) return 0; }
        else if (*p == '/') { ++p; if (!parse_factor(q, -sign)) return 0; }
        else return 1;
    }
}

static void trim(char *s) {
    char *a = s;
    while (*a == ' ' || *a == '\t') ++a;
    memmove(s, a, strlen(a) + 1);
    size_t n = strlen(s);
    while (n && (s[n - 1] == ' ' || s[n - 1] == '\t' || s[n - 1] == '\r' || s[n - 1] == '\n' || s[n - 1] == '.'))
        s[--n] = 0;
}

static int parse_unit(const char *text, Q *q) {
    char s[256];
    snprintf(s, sizeof s, "%s", text);
    trim(s);
    q->f = 1; q->off = 0;
    memset(q->d, 0, sizeof q->d);
    if (!*s) return 1;   /* без единицы */
    if (unit_exact(s, q)) return 1;
    /* «мм рт. ст.» и подобные с точкой в конце: trim срезал точку */
    char dotted[260];
    snprintf(dotted, sizeof dotted, "%s.", s);
    if (unit_exact(dotted, q)) return 1;
    p = s;
    if (!parse_product(q, 1)) return 0;
    skip_spaces();
    if (*p) { snprintf(err, sizeof err, "не разобрать единицу около «%s»", p); return 0; }
    return 1;
}

/* «72 км/ч», «2,5 кг», «1 000 м», «-40 °C», «1.5e3 Па» -> число и остаток */
static int parse_value(const char *s, double *v, const char **rest) {
    char num[128];
    size_t n = 0;
    while (*s == ' ') ++s;
    if (*s == '-' || *s == '+') num[n++] = *s++;
    while (*s && n + 1 < sizeof num) {
        if (isdigit((unsigned char)*s)) num[n++] = *s++;
        else if (*s == ' ' && isdigit((unsigned char)s[1]) && isdigit((unsigned char)s[2]) && isdigit((unsigned char)s[3])
                 && !isdigit((unsigned char)s[4])) ++s;           /* 1 000 */
        else break;
    }
    if ((*s == '.' || *s == ',') && isdigit((unsigned char)s[1])) {
        num[n++] = '.'; ++s;
        while (isdigit((unsigned char)*s) && n + 1 < sizeof num) num[n++] = *s++;
    }
    if ((*s == 'e' || *s == 'E') && (isdigit((unsigned char)s[1]) || s[1] == '-' || s[1] == '+')) {
        num[n++] = *s++;
        if (*s == '-' || *s == '+') num[n++] = *s++;
        while (isdigit((unsigned char)*s) && n + 1 < sizeof num) num[n++] = *s++;
    }
    num[n] = 0;
    if (n == 0 || (n == 1 && (num[0] == '-' || num[0] == '+'))) { snprintf(err, sizeof err, "нет числа"); return 0; }
    *v = strtod(num, NULL);
    *rest = s;
    return 1;
}

static void si_name(const Q *q, char *out, size_t size) {
    static const struct { const char *name; int d[ND]; } NAMED[] = {
        {"Н", FN}, {"Дж", EN}, {"Вт", PW}, {"Па", PR}, {"Гц", {0,0,-1,0,0,0,0}}, {"В", {2,1,-3,-1,0,0,0}},
        {"Ом", {2,1,-3,-2,0,0,0}}, {"Кл", {0,0,1,1,0,0,0}},
    };
    for (size_t i = 0; i < sizeof NAMED / sizeof NAMED[0]; ++i)
        if (memcmp(q->d, NAMED[i].d, sizeof q->d) == 0) { snprintf(out, size, "%s", NAMED[i].name); return; }
    char num[128] = "", den[128] = "";
    for (int i = 0; i < ND; ++i) {
        int k = q->d[i];
        if (!k) continue;
        char part[16];
        if (abs(k) == 1) snprintf(part, sizeof part, "%s", DIM_NAME[i]);
        else snprintf(part, sizeof part, "%s%d", DIM_NAME[i], abs(k));
        char *dst = k > 0 ? num : den;
        if (*dst) strncat(dst, "*", sizeof num - strlen(dst) - 1);
        strncat(dst, part, sizeof num - strlen(dst) - 1);
    }
    if (!*num && !*den) snprintf(out, size, "(без единиц)");
    else if (!*den) snprintf(out, size, "%s", num);
    else snprintf(out, size, "%s/%s", *num ? num : "1", den);
}

static void fmt(double v, char *out, size_t size) {
    if (v != 0 && (fabs(v) >= 1e12 || fabs(v) < 1e-6)) snprintf(out, size, "%.6g", v);
    else {
        snprintf(out, size, "%.10f", v);
        char *dot = strchr(out, '.');
        if (dot) {
            /* 10 знаков после точки, хвост нулей прочь; 4.999999999 -> 5 */
            double r = round(v * 1e9) / 1e9;
            snprintf(out, size, "%.9f", r);
            size_t n = strlen(out);
            while (n && out[n - 1] == '0') out[--n] = 0;
            if (n && out[n - 1] == '.') out[--n] = 0;
        }
    }
    if (strcmp(out, "-0") == 0) snprintf(out, size, "0");
}

static int run(const char *name, char *args, char *out, size_t size) {
    double v;
    const char *rest;
    Q from, to;
    char a[512] = "", b[512] = "";
    if (strcmp(name, "ПЕРЕВЕСТИ") == 0) {
        /* последняя запятая, за которой не цифра: «2,5 км, м» */
        char *cut = NULL;
        for (char *c = args; *c; ++c)
            if (*c == ',' && !isdigit((unsigned char)c[1])) cut = c;
        if (!cut) { snprintf(err, sizeof err, "нужно: ПЕРЕВЕСТИ(число единица, единица)"); return 0; }
        *cut = 0;
        snprintf(a, sizeof a, "%s", args);
        snprintf(b, sizeof b, "%s", cut + 1);
    } else if (strcmp(name, "СИ") == 0) {
        snprintf(a, sizeof a, "%s", args);
    } else {
        snprintf(err, sizeof err, "неизвестная команда %s", name);
        return 0;
    }
    if (!parse_value(a, &v, &rest)) return 0;
    if (!parse_unit(rest, &from)) return 0;
    double si = v * from.f + from.off;
    char vs[64], us[128];
    if (strcmp(name, "СИ") == 0) {
        fmt(si, vs, sizeof vs);
        si_name(&from, us, sizeof us);
        snprintf(out, size, "%s %s", vs, us);
        return 1;
    }
    trim(b);
    if (!parse_unit(b, &to)) return 0;
    if (memcmp(from.d, to.d, sizeof from.d) != 0) {
        char u1[128], u2[128];
        si_name(&from, u1, sizeof u1);
        si_name(&to, u2, sizeof u2);
        snprintf(err, sizeof err, "разные величины: [%s] нельзя перевести в [%s]", u1, u2);
        return 0;
    }
    fmt((si - to.off) / to.f, vs, sizeof vs);
    snprintf(out, size, "%s %s", vs, b);
    return 1;
}

int main(void) {
    char line[1024];
    while (fgets(line, sizeof line, stdin)) {
        trim(line);
        if (!*line) continue;
        char *open = strchr(line, '('), *close = strrchr(line, ')');
        if (!open || !close || close < open) { printf("%s = ошибка: нужно КОМАНДА(аргументы)\n", line); continue; }
        char name[64], args[512], out[256];
        size_t nl = (size_t)(open - line);
        if (nl >= sizeof name) nl = sizeof name - 1;
        memcpy(name, line, nl); name[nl] = 0;
        trim(name);
        size_t na = (size_t)(close - open - 1);
        if (na >= sizeof args) na = sizeof args - 1;
        memcpy(args, open + 1, na); args[na] = 0;
        err[0] = 0;
        if (run(name, args, out, sizeof out)) printf("%s = %s\n", line, out);
        else printf("%s = ошибка: %s\n", line, err);
    }
    return 0;
}
