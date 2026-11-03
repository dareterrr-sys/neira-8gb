"""Neira's textbook from the original (31.10, the author: «не пересказывай своими словами, бери оригинал»):
D. E. Rozental, «Справочник по русскому языку. Практическая стилистика», recognised text. Paragraphs (§) and their
numbered points are taken as they are (only page marks and line breaks mended). An EGE task names its error kinds
(task 8) or means of expression (task 22) and gets the points of the paragraphs about exactly those, the way a
person opens the reference book on the right paragraph and finds the right point.
sections_for(task_text, n) -> the text or ''."""
import re
from functools import lru_cache

import os

# the two OCR readings voted word by word (textbooks/merge_ocr.py) when there is that file, else the first reading
_FIRST = r"D:\AI\Учебники по русскому языку\text\rozental_d_e_spravochnik_po_russkomu_yazyku_prakticheskaya_s.txt"
_MERGED = r"D:\AI\Учебники по русскому языку\text\rozental_stilistika_merged.txt"
BOOK = _MERGED if os.path.exists(_MERGED) else _FIRST


def _contents_line():
    """The table of contents at the end repeats the headings: it starts where «§ 1. Понятие о функциональных
    стилях» appears the second time."""
    lines = open(BOOK, encoding="utf-8").read().splitlines()
    at = [i for i, l in enumerate(lines) if re.match(r"^\W*[$§85]\s?1[.,]\s+Понятие о функциональных", l)]
    return at[-1] if len(at) > 1 else len(lines)


CONTENTS_LINE = _contents_line()
# N. S. Valgina, «Современный русский язык. Синтаксис» (2003, a text PDF, no OCR): § 135 «Косвенная речь» - the
# rule Rozental's stylistics does not have
VALGINA = r"D:\AI\Учебники по русскому языку\text\Валгина, Н.С. Современный русский язык; Синтаксис. М. Высш. шк., 2003. 416 с. Расп. в FR8 (sl).txt"

# what the task names -> [(paragraph, which of its points: a regex over the point's text, None = the whole paragraph)];
# ("В", 135) = Valgina's paragraph. Whole points, never cut by length (31.10: a length limit cut off § 96 point 4,
# «неправильное употребление союзов» - exactly the «сказал, что будто» errors)
ERRORS = [   # task 8
    (r"числительн", [(41, None), (40, r"^(4|8|13)\.")]),   # all words of a compound numeral decline; оба/обе; полтора
    (r"подлежащим и сказуемым", [(67, None), (68, None)]),  # кто/те, кто; жюри, «Известия», аббревиатуры
    (r"несогласованным приложением", [(76, None)]),
    # «по приезде» is in § 79 point 7, «согласно приказу» in § 80 point 0 (the § 80 heading was lost to OCR)
    (r"падежной|предложно-падежной|управляем", [(79, r"по приезде|по окончании"), (80, None), (82, None)]),
    (r"однородными членами", [(85, None), (89, r"^(2|5|8|9|10)\.")]),
    (r"сложного предложения|сложноподчин", [(96, None)]),
    (r"(?<!дее)причастным оборотом", [(98, r"ошибк|определяем|порядок|будущего|отрыв|согласован")]),
    (r"деепричастным оборотом", [(99, r"подлежащ|безличн|страдательн|ошибк|действующ")]),
    (r"косвенной речью", [(("В", 135), None)]),
    (r"видо-временной", [(49, r"соотнес|одновремен|последовател"), (51, r"соотнес|видов")]),
]
MEANS = [    # task 22
    (r"эпитет", [(106, None)]), (r"сравнени", [(107, None)]), (r"метафор", [(108, None)]), (r"метоними", [(109, None)]),
    (r"синекдох", [(110, None)]), (r"гипербол|литот", [(111, None)]), (r"ирони", [(112, None)]),
    (r"аллегори", [(113, None)]), (r"олицетворени", [(114, None)]), (r"перифраз", [(115, None)]),
    (r"анафор|эпифор", [(116, None)]), (r"параллелизм", [(117, None)]), (r"антитез|оксюморон", [(118, None)]),
    (r"градаци", [(119, None)]), (r"инверси", [(120, None)]), (r"эллипсис", [(121, None)]),
    (r"умолчани", [(122, None)]), (r"риторическое обращение", [(123, None)]),
    (r"риторический вопрос|риторическое восклицание", [(124, None)]), (r"многосоюзи|бессоюзи", [(125, None)]),
]


@lru_cache(maxsize=1)
def _morph():
    import pymorphy3
    return pymorphy3.MorphAnalyzer()


def _rejoin(m):
    """A word carried over at a hyphen: «обстоятель-|ственных» is one word, «профессионально-|технической» keeps its
    hyphen (31.10: the plain join made «профессиональнотехнической»). The dictionary decides; unknown -> one word."""
    left, right = m.group(1), m.group(2)
    morph = _morph()
    if morph.word_is_known(left + right):
        return left + right
    lo = left.lower()
    # only the real kinds of hyphenated words keep the hyphen; pymorphy «knows» scraps like «ос», «ре», «вс», so a
    # bare «both parts known» kept OCR breaks («ос-тал», «являют-ея», «Розен-таль»)
    particle = (right in ("то", "либо", "нибудь", "таки") or lo in ("кое", "кой")
                or (right == "ка" and "impr" in morph.parse(left)[0].tag))   # «дай-ка», not «погодиш-ка»
    repeat = lo == right
    def noun(w):   # noqa: E306
        p = morph.parse(w)[0]
        return morph.word_is_known(w) and "NOUN" in p.tag and len(w) >= 4
    compound_adj = (len(left) >= 5 and lo.endswith(("о", "е")) and morph.word_is_known(left) and len(right) >= 5
                    and morph.word_is_known(right) and "ADJF" in morph.parse(right)[0].tag)
    apposition = noun(left) and noun(right) and morph.parse(left)[0].tag.case == morph.parse(right)[0].tag.case
    return left + "-" + right if (particle or repeat or compound_adj or apposition) else left + right


def clean(text):
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l and not re.fullmatch(r"=== стр\. \d+ ===|\d{1,3}|[_`'‘’|.,]+", l)]
    text = "\n".join(lines)
    text = re.sub(r"([А-Яа-яЁё]+)[-­]\n([а-яё]+)", _rejoin, text)   # hyphenated line breaks
    text = re.sub(r"(?<![.:!?»])\n(?=[а-яё(«—–-])", " ", text)  # a sentence broken across lines
    return re.sub(r"[ \t]{2,}", " ", text).strip()


SPANS = {}


@lru_cache(maxsize=1)
def paragraphs():
    """-> {number: (heading, [points])}: a paragraph's text split at its numbered points «1.», «2.»..."""
    lines = open(BOOK, encoding="utf-8").read().splitlines()[:CONTENTS_LINE]
    # OCR spoils the «§»: «$ 80.», «.- $ 80.», «5 83.», «8 22.», «$ 24,» - a heading is any of these with a capital
    # word after it, and the numbers must go up by 1-3 (a stray «5 3.» in a list or a spoilt «$ 2.» is not a heading)
    heads, last = [], 0
    for i, l in enumerate(lines):
        m = re.match(r"^[.\-|\s]*[$§85]\s?(\d{1,3})[.,]\s+[А-ЯЁ]", l)
        if m and last < int(m.group(1)) <= last + 3:
            heads.append((i, int(m.group(1))))
            last = int(m.group(1))
    # a heading the number of which OCR lost entirely («$ И.» for 11, «$ 2.» for 17) is found by its title from the
    # table of contents, between its neighbours (31.10: without it § 11 and § 17 were cut off with an exercise)
    toc = {}
    for l in open(BOOK, encoding="utf-8").read().splitlines()[CONTENTS_LINE:]:
        m = re.match(r"^\W*[$§85]\s?(\d{1,3})[.,]\s+(.+)", l)
        if m:
            toc.setdefault(int(m.group(1)), m.group(2))
    key = lambda s: re.sub(r"[^а-яё]", "", s.lower())[:22]   # noqa: E731
    found = {n for _, n in heads}
    for n, title in toc.items():
        if n in found or len(key(title)) < 12:
            continue
        lo = max([i for i, k in heads if k < n], default=0)
        hi = min([i for i, k in heads if k > n], default=len(lines))
        at = next((i for i in range(lo + 1, hi) if key(lines[i]).find(key(title)[:16]) >= 0 and
                   re.match(r"^\W*[$§85]", lines[i])), None)
        if at is not None:
            heads.append((at, n))
    # a paragraph also ends at a chapter heading («ГЛАВА 6» - chapter 6 has no paragraphs at all) and at a block of
    # revision exercises; an exercise («Упражнение 22») runs from its line to the next of these boundaries
    bounds = sorted({i for i, _ in heads} | {i for i, l in enumerate(lines)
                                             if re.match(r"^(ГЛАВА\s*\d|ПОВТОРИТЕЛЬНЫЕ УПРАЖНЕНИЯ)", l.strip())})
    out = {}
    for i, n in sorted(heads):
        end = next((b for b in bounds if b > i), len(lines))
        chunk = lines[i:end]
        cut = next((j for j, l in enumerate(chunk) if re.match(r"^\W*Упражнени[ея]\s*\d", l.strip())), len(chunk))
        text = clean("\n".join(chunk[:cut]))
        head, _, body = text.partition("\n")
        points = [p.strip() for p in re.split(r"\n(?=\d{1,2}\.\s)", body) if p.strip()]
        title = re.sub(r"^\W*[$§85]?\s?(\d{1,3}|[ИЗ])?[.,]?\s*", "", head, count=1)   # «.- $ 80.», «$ И.»
        out[n] = (f"§ {n}. {title}", points)
        SPANS[n] = (i, i + cut)   # the lines of the merged book the paragraph was taken from (for proofreading)
    return out


@lru_cache(maxsize=1)
def valgina():
    """-> {number: (heading, [points])} of Valgina's syntax: «§ 135. КОСВЕННАЯ РЕЧЬ» ... (a text layer, the soft
    hyphen at line ends is U+FFFE)."""
    text = open(VALGINA, encoding="utf-8").read().replace("\ufffe\n", "").replace("\ufffe", "")
    lines = text.splitlines()
    heads = [(i, int(m.group(1))) for i, l in enumerate(lines) if (m := re.match(r"^§ (\d+)\. [А-ЯЁ]", l.strip()))]
    out = {}
    for (i, n), nxt in zip(heads, heads[1:] + [(len(lines), 0)]):
        body = clean("\n".join(lines[i + 1:nxt[0]]))
        out.setdefault(n, (lines[i].strip(), [body]))
    return out


def sections_for(task_text, n):
    """Whole points of the paragraphs about the kinds the task names, in the order of the task's list."""
    table = ERRORS if n == 8 else MEANS if n == 22 else []
    parts = []
    for rx, refs in table:
        if not re.search(rx, task_text, re.I):
            continue
        chunk = []
        for p, point_rx in refs:
            book, who = (valgina(), "Валгина, «Синтаксис»") if isinstance(p, tuple) else (paragraphs(), "Розенталь")
            key = p[1] if isinstance(p, tuple) else p
            if key not in book:
                continue
            head, points = book[key]
            pick = points if point_rx is None else [x for x in points if re.search(point_rx, x, re.I)]
            if pick:
                chunk.append(f"{who}, {head}\n" + "\n".join(pick))
        if chunk:
            parts.append("\n\n".join(chunk))
    return "\n\n".join(parts)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    t = ("А) нарушение связи между подлежащим и сказуемым Б) неправильное построение предложения с деепричастным "
         "оборотом В) ошибка в употреблении имени числительного Г) нарушение в построении предложения с несогласованным "
         "приложением Д) неправильное употребление падежной (предложно-падежной) формы управляемого слова")
    s = sections_for(t, 8)
    print(len(s), "символов\n", s[:3000])
