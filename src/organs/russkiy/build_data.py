"""Build the plain word lists the C++ russkiy organ loads (one word per line, UTF-8, lower case, sorted):
  opencorpora.txt  - every word form of the OpenCorpora dictionary (taken from pymorphy3-dicts-ru: opencorpora.org is down)
  accents.txt      - word<TAB>stressed form from RUAccent's dictionary ('+' before the stressed vowel); homographs get
                     every variant on one line, comma separated
  fipi_stress.txt  - the FIPI orthoepic list 2026 for task 4 (word with the stressed vowel in upper case), from the PDF
Usage (russkiy/.venv): python build_data.py
"""
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RUACC = r"D:\AI\ruaccent\.venv\Lib\site-packages\ruaccent\dictionary"


def opencorpora():
    import pymorphy3
    m = pymorphy3.MorphAnalyzer()
    words = set()
    for word, _tag, _norm, _para, _idx in m.dictionary.iter_known_words():
        if re.fullmatch(r"[а-яё-]+", word):
            words.add(word)
    return words


def accents():
    acc = json.load(gzip.open(os.path.join(RUACC, "accents.json.gz")))
    omo = json.load(gzip.open(os.path.join(RUACC, "omographs.json.gz")))
    out = {w: [s] for w, s in acc.items()}
    for w, variants in omo.items():
        out[w] = list(variants)
    return out


def fipi():
    import pdfplumber
    text = "\n".join(p.extract_text() or "" for p in pdfplumber.open(os.path.join(DATA, "fipi_fonetika_2026.pdf")).pages)
    open(os.path.join(DATA, "fipi_fonetika_2026.txt"), "w", encoding="utf-8").write(text)
    # the list runs from «Имена существительные» to the first «Обратите внимание!»; an entry is any word with exactly
    # one upper-case letter, a vowel (аэропОрты, Иксы, and the forms in the notes: «бОроду, ... сущ. бородА»)
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip() == "Имена существительные")
    end = next(i for i, l in enumerate(lines) if i > start and l.startswith("Обратите внимание!"))
    heads = {"Имена существительные", "Имена прилагательные", "Глаголы", "Причастия и отглагольные прилагательные",
             "Деепричастия", "Наречия"}
    found = []
    for l in lines[start:end]:
        l = l.strip()
        if l in heads or l.startswith("Навигатор") or re.match(r"^\d", l):
            continue
        for w in re.findall(r"[а-яёА-ЯЁ]+", l):
            ups = [c for c in w if c.isupper()]
            if len(ups) == 1 and ups[0] in "АЕЁИОУЫЭЮЯ" and len(w) > 1:
                found.append(w)
    seen, uniq = set(), []
    for w in found:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
    return uniq


def pack(entries, path):
    """Sorted byte strings -> uint32 N, uint32 offsets[N+1], blob (what russkiy.cpp reads; cp1251: 1 byte a letter)."""
    import struct
    entries = sorted(set(entries))
    offs, pos = [], 0
    for e in entries:
        offs.append(pos)
        pos += len(e)
    offs.append(pos)
    with open(path, "wb") as f:
        f.write(struct.pack("<I", len(entries)))
        f.write(struct.pack(f"<{len(offs)}I", *offs))
        f.write(b"".join(entries))
    return len(entries)


POS_BITS = {"VERB": 1, "INFN": 1, "GRND": 2, "PRTF": 4, "PRTS": 8, "ADJF": 16, "ADJS": 32, "NOUN": 64, "ADVB": 128}
POS_BITS2 = {"COMP": 1, "NPRO": 2, "NUMR": 4, "PREP": 8, "CONJ": 16, "PRCL": 32, "PRED": 64}


def oc_flags():
    """word -> 3 bytes of grammar bits over all its parses (russkiy.cpp oc_flags):
    byte 0: 1 verb 3rd person sing, 2 verb 3rd person plur, 4 nominative sing (noun, pronoun, adjective), 8 nominative
            plur, 16 can be accusative, 32 verb 2nd person sing, 64 can be instrumental, 128 can be genitive;
    byte 1: part of speech POS_BITS; byte 2: POS_BITS2 + 128 can be dative."""
    import pymorphy3
    m = pymorphy3.MorphAnalyzer()
    flags = {}
    for word, tag, _norm, _para, _idx in m.dictionary.iter_known_words():
        if not re.fullmatch(r"[а-яё-]+", word):
            continue
        f = 0
        if "VERB" in tag and tag.person == "3per":
            f |= 1 if tag.number == "sing" else 2
        if "VERB" in tag and tag.person == "2per" and tag.number == "sing":
            f |= 32
        if tag.POS in ("NOUN", "NPRO", "ADJF") and tag.case == "nomn":
            f |= 4 if tag.number == "sing" else 8
        f |= {"accs": 16, "ablt": 64, "gent": 128}.get(tag.case, 0)
        f |= POS_BITS.get(tag.POS, 0) << 8
        f |= POS_BITS2.get(tag.POS, 0) << 16
        if tag.case == "datv":
            f |= 128 << 16
        flags[word] = flags.get(word, 0) | f
    return flags


def binaries():
    """opencorpora.bin: word 0x00 grammar bits (oc_flags); accents.bin: word 0x00 stress positions (1-based letter
    index, one byte per variant)."""
    fl = oc_flags()
    oc = [w.encode("cp1251") + b"\0" + f.to_bytes(3, "little") for w, f in fl.items()]
    print("opencorpora.bin:", pack(oc, os.path.join(DATA, "opencorpora.bin")))
    acc = []
    for line in open(os.path.join(DATA, "accents.txt"), encoding="utf-8"):
        w, variants = line.rstrip("\n").split("\t")
        try:
            key = w.encode("cp1251")
        except UnicodeEncodeError:
            continue
        pos = sorted({v.index("+") + 1 for v in variants.split(",") if "+" in v})
        if pos and all(p <= 255 for p in pos):
            acc.append(key + b"\0" + bytes(pos))
    print("accents.bin:", pack(acc, os.path.join(DATA, "accents.bin")))
    # words that dictionaries often spell with е but are written with ё (RUAccent yo_words): е-form 0x00 ё positions
    yo = json.load(gzip.open(os.path.join(RUACC, "yo_words.json.gz")))
    ent = []
    for e, y in yo.items():
        try:
            ent.append(e.encode("cp1251") + b"\0" + bytes(i + 1 for i, c in enumerate(y) if c == "ё"))
        except (UnicodeEncodeError, ValueError):
            pass
    print("yo.bin:", pack(ent, os.path.join(DATA, "yo.bin")))


if __name__ == "__main__" and sys.argv[1:] == ["bin"]:
    binaries()
    sys.exit()

if __name__ == "__main__":
    oc = opencorpora()
    open(os.path.join(DATA, "opencorpora.txt"), "w", encoding="utf-8").write("\n".join(sorted(oc)) + "\n")
    print("opencorpora:", len(oc))
    ac = accents()
    with open(os.path.join(DATA, "accents.txt"), "w", encoding="utf-8") as f:
        for w in sorted(ac):
            f.write(w + "\t" + ",".join(ac[w]) + "\n")
    print("accents:", len(ac), "of them homographs:", sum(len(v) > 1 for v in ac.values()))
    fp = fipi()
    open(os.path.join(DATA, "fipi_stress.txt"), "w", encoding="utf-8").write("\n".join(fp) + "\n")
    print("fipi:", len(fp), fp[:15], fp[-10:])
