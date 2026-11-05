"""Stress organ, text half: WHICH words of a sentence to check and HOW they must be stressed.

Sources (the author's Russian library, neira-tools/russkiy/data):
  accents.txt      word<TAB>variants with '+' before the stressed vowel; >1 variant = homograph (from RUAccent)
  fipi_stress.txt  FIPI orthoepic list 2026 (stressed vowel in upper case)
  OpenCorpora      morphology (pymorphy3, the dictionary opencorpora.txt was built from) - a homograph by context
  orfoep_ran.tsv   the RAN orthoepic dictionary (neira-tools/knowledge/russkiy/stress_norm, department «Лексикография»,
                   05.11; author: «Да, норма из РАН», «Да, передай»): form, stress(es), article
A '+' already in the text (the voice's own stress mark from the stress service) is what the voice was TOLD to say.

Expected stress («как надо») - ONLY from the norm (author via HQ, 04.11: the edited library only; accents.txt is
not edited - two variants there do not mean both are right: звонит -> зв+онит,звон+ит; the norm is FIPI):
  1. FIPI 2026 (fipi_stress.txt);
  1b. RAN (orfoep_ran.tsv): every stress of the form's rows is a norm (сверлит: св+ерлит and сверл+ит - both right);
      rows of different articles with different stresses = a homograph (з+амок / зам+ок) -> not decided here; the
      dictionary is selective, so when accents.txt knows a reading RAN lacks (сорока: bird) and morphology gives a lemma
      no RAN article has -> not decided either;
  2. context rule (OpenCorpora morphology) for the «года/годА» class: noun whose plural moves the stress to the final
     а/я; the previous word in gent/sing or a numeral 2-4 -> singular (stem stress), in nomn|accs/plur -> plural
     (accents.txt only lists the two candidate stresses);
  otherwise expected = None («не уверен»: the organ still says what it heard).
  The '+' mark (what the voice was TOLD by RUAccent) and a single accents.txt variant are kept as "told" / "dict" for
  information, not as the norm; a mark that contradicts FIPI is reported.
Checked words (accents.txt and the marks are used ONLY as this list): homographs, FIPI words, words with a '+',
and (STRESS_RAN_CHECK=all) every RAN word. A word whose every vowel is a norm is not checked.

Runs in the russkiy venv (pymorphy3). Usage: python stress_text.py in.json out.json [--all]
       python stress_text.py --serve   (JSON lines on stdin/stdout, for stress_judge_service.py)
  --all: also every word of 2+ syllables with one dictionary stress (checked, but «как надо» still only from the norm)
  in.json  = ["sentence", ...]
  out.json = [{"text": clean sentence, "words": [{"w", "stress", "check", "expected", "why", "variants"}]}]
  stress / expected / variants = 0-based index of the stressed VOWEL in the word (not the letter).
"""
import json
import os
import re
import sys

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "russkiy", "data")
VOW = "аеёиоуыэюя"
WORD_RE = re.compile(r"[а-яёА-ЯЁ+]+")


RAN_CHECK = os.environ.get("STRESS_RAN_CHECK", "doubtful")
RAN_TSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge", "russkiy",
                       "stress_norm", "orfoep_ran.tsv")
_RAN = None


def load_ran():
    """form -> [(set of vowel indexes, article with '+')]"""
    global _RAN
    if _RAN is None:
        _RAN = {}
        with open(RAN_TSV, encoding="utf-8") as f:
            next(f)
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3 or "+" not in parts[1]:
                    continue
                vs = {from_plus(v) for v in parts[1].split("|") if "+" in v}
                _RAN.setdefault(parts[0], []).append((vs, parts[2]))
    return _RAN


def ran_norm(w, acc_variants):
    """(sorted acceptable vowel indexes, why) from RAN, or (None, why) / None if the form is not in RAN."""
    rows = load_ran().get(w)   # no е->ё guessing: «небо» must not take «нёбо»'s row
    if not rows:
        return None
    by_art = {}
    for vs, art in rows:
        by_art.setdefault(art, set()).update(vs)
    sets = {frozenset(v) for v in by_art.values()}
    arts = ", ".join(sorted(by_art))
    if len(sets) > 1:
        return None, f"РАН: омограф ({arts}) — по форме не решён"
    ok = set(next(iter(sets)))
    if len(acc_variants) > 1 and not set(acc_variants) <= ok:   # another reading RAN does not list?
        lemmas = {p.normal_form.replace("ё", "е") for p in morph().parse(w) if p.score >= 0.05}
        have = {a.replace("+", "").replace("ё", "е") for a in by_art}
        if not lemmas <= have:
            return None, f"РАН: только «{arts}», а форма бывает и от «{', '.join(sorted(lemmas - have))}»"
    return sorted(ok), f"РАН (статья {arts})"


def vowel_index(word, letter_pos):
    """0-based vowel ordinal of the vowel at letter_pos."""
    return sum(1 for c in word[:letter_pos] if c in VOW)


def from_plus(variant):
    """'г+ода' -> 0 (the vowel after '+')."""
    i = variant.index("+")
    return vowel_index(variant.replace("+", ""), i)


class AccentsIndex:
    """Binary search in the sorted accents.txt (build_data.py writes it sorted; UTF-8 byte order = code point order):
    a word costs ~22 reads instead of scanning 3.2M lines - for the live judge (stress_judge_service.py)."""

    def __init__(self, path):
        import mmap
        self.f = open(path, "rb")
        self.m = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)

    def _line_at(self, pos):
        if pos > 0:
            pos = self.m.find(b"\n", pos - 1) + 1
            if pos == 0:
                return None, len(self.m)
        end = self.m.find(b"\n", pos)
        end = len(self.m) if end < 0 else end
        return self.m[pos:end], end + 1

    def get(self, word):
        key = word.encode("utf-8")
        lo, hi = 0, len(self.m)
        while lo < hi:
            mid = (lo + hi) // 2
            line, nxt = self._line_at(mid)
            if line is None:
                hi = mid
                continue
            k = line.split(b"\t", 1)[0]
            if k < key:
                lo = nxt
            else:
                hi = mid
        line, _ = self._line_at(lo)
        if line and line.split(b"\t", 1)[0] == key:
            return line.decode("utf-8").split("\t", 1)[1].strip()
        return None


_ACC = None


def load_fipi():
    fipi = {}
    for line in open(os.path.join(DATA, "fipi_stress.txt"), encoding="utf-8"):
        w = line.strip()
        ups = [i for i, c in enumerate(w) if c in VOW.upper()]
        if len(ups) == 1:
            fipi[w.lower()] = vowel_index(w.lower(), ups[0])
    return fipi


def load_dicts(needed):
    global _ACC
    if _ACC is None:
        _ACC = AccentsIndex(os.path.join(DATA, "accents.txt"))
    acc = {}
    for w in needed:
        v = _ACC.get(w)
        if v:
            acc[w] = sorted({from_plus(x) for x in v.split(",") if "+" in x})
    return acc, load_fipi()


_M = None


def morph():
    global _M
    if _M is None:
        import pymorphy3
        _M = pymorphy3.MorphAnalyzer()
    return _M


def context_rule(words, i, variants):
    """The «года» class: returns (vowel index, reason) or None."""
    w = words[i]
    nv = sum(c in VOW for c in w)
    if len(variants) != 2 or w[-1] not in "ая" or (nv - 1) not in variants:
        return None
    parses = [p for p in morph().parse(w) if p.tag.POS == "NOUN"]
    sg = any(p.tag.number == "sing" and p.tag.case == "gent" for p in parses)
    pl = any(p.tag.number == "plur" and p.tag.case in ("nomn", "accs") for p in parses)
    if not (sg and pl) or i == 0:
        return None
    stem = [v for v in variants if v != nv - 1][0]
    prev = words[i - 1]
    if prev in ("два", "две", "три", "четыре", "оба", "обе", "полтора", "полторы"):
        return stem, f"OpenCorpora: «{prev} {w}» — числительное 2–4 → род. п. ед. ч."
    pp = [p for p in morph().parse(prev) if p.tag.POS in ("ADJF", "PRTF", "NUMR", "NPRO")]
    if not pp:
        return None
    best = pp[0].tag
    if best.case == "gent" and best.number == "sing":
        return stem, f"OpenCorpora: «{prev}» род. п. ед. ч. → «{w}» род. п. ед. ч."
    if best.number == "plur" and best.case in ("nomn", "accs"):
        return nv - 1, f"OpenCorpora: «{prev}» мн. ч. → «{w}» им./вин. п. мн. ч."
    return None


def analyse(sentences, check_all=False):
    toks = [[t for t in WORD_RE.findall(s)] for s in sentences]
    needed = {t.replace("+", "").lower() for ts in toks for t in ts}
    acc, fipi = load_dicts(needed)
    out = []
    for s, ts in zip(sentences, toks):
        clean = [t.replace("+", "").lower() for t in ts]
        words = []
        for i, (t, w) in enumerate(zip(ts, clean)):
            nv = sum(c in VOW for c in w)
            variants = acc.get(w, [])
            mark = from_plus(t.lower()) if "+" in t else None
            if "ё" in w:   # ё is always stressed
                variants = [vowel_index(w, w.index("ё"))]
            homo = len(variants) > 1
            ran = ran_norm(w, variants) if nv >= 2 else None
            # which words are checked: the doubtful ones (homograph, FIPI, a '+' mark) - RAN gives their norm; with
            # STRESS_RAN_CHECK=all also every RAN word (05.11 on the interview texts: the judge would run on 152 of
            # 179 sentences instead of 43, and flag 22 words instead of 4 - not checked by ear)
            check = nv >= 2 and (homo or w in fipi or mark is not None
                                 or (ran is not None and RAN_CHECK == "all") or (check_all and len(variants) == 1))
            expected, why, expected_any = None, "", None
            ctx = context_rule(clean, i, variants) if homo else None
            if w in fipi:
                expected, why = fipi[w], "ФИПИ 2026"
                if ran and ran[0] and fipi[w] in ran[0] and len(ran[0]) > 1:
                    expected_any = ran[0]
                    why += f"; {ran[1]}: допустимы {len(ran[0])} варианта"
            elif ran and ran[0]:
                expected_any = ran[0]
                expected, why = ran[0][0], ran[1]
            elif ctx:
                expected, why = ctx
            elif ran:
                why = ran[1]
            elif homo:
                why = "омограф: по форме не решён"
            else:
                why = "нет в ФИПИ и РАН: норма не задана"
            if expected_any is None and expected is not None:
                expected_any = [expected]
            if expected_any is not None and len(expected_any) >= nv:   # every vowel is a norm: nothing to check
                check = False
            if expected is not None and mark is not None and mark not in expected_any:
                why += f"; пометка «+» спорит (на гласной {mark + 1})"
            # stress used to build the rest of the sentence's sounds (not checked words): best guess
            if expected is not None:
                stress = expected
            elif mark is not None:
                stress = mark
            elif variants:
                stress = variants[0]
            else:
                stress = max(0, nv - 2) if nv >= 2 else 0
            words.append({"w": w, "stress": stress, "check": bool(check), "expected": expected,
                          "expected_any": expected_any, "why": why,
                          "variants": variants, "fipi": w in fipi, "told": mark,
                          "dict": variants[0] if len(variants) == 1 else None})
        out.append({"text": " ".join(clean), "words": words})
    return out


if __name__ == "__main__":
    if sys.argv[1:2] == ["--serve"]:   # one JSON list of sentences per stdin line -> one JSON answer per stdout line
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
        morph()
        print(json.dumps({"ready": True}), flush=True)
        for line in sys.stdin:
            try:
                print(json.dumps(analyse(json.loads(line)), ensure_ascii=False), flush=True)
            except Exception as e:
                print(json.dumps({"error": repr(e)}), flush=True)
        sys.exit()
    src = json.load(open(sys.argv[1], encoding="utf-8"))
    json.dump(analyse(src, check_all="--all" in sys.argv), open(sys.argv[2], "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
