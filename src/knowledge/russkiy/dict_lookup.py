# -*- coding: utf-8 -*-
"""Орган «словарь»: толкования из локального «Толкового словаря русского языка»
С. И. Ожегова и Н. Ю. Шведовой (dict_ozhegov.txt) + ядро частотной лексики
(ref_lex_minimum.md, контексты и толкования).

API:
    from dict_lookup import gloss, is_known
    gloss('слово')            -> строка-толкование или '' (не найдено)
    is_known('слово')         -> bool

CLI:
    python dict_lookup.py слово [слово ...]
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DICT = os.path.join(HERE, 'dict_ozhegov.txt')
CORE = os.path.join(HERE, 'ref_lex_minimum.md')

_HEAD = re.compile(r'^([А-ЯЁ][А-ЯЁ0-9]*(?:\.\.\.)?)\s*[, ]')
_DERIV = re.compile(r'\s+(?:II|11|2)\s+(?:прил\.?|сущ\.?|нареч\.?|межд\.?|союз|частиц)')

_INDEX = None


def _clean_def(s):
    s = _DERIV.split(s, 1)[0]
    s = re.sub(r'\s+', ' ', s).strip()
    if not s:
        return ''
    s = s.rstrip(' .,;:-')
    s = s.replace('|', '/')
    return s[:320]


def _build_index():
    """-> {лемма_нижним: толкование} (омонимы объединены, первый вариант)."""
    idx = {}
    try:
        text = open(DICT, encoding='utf-8', errors='ignore').read()
    except FileNotFoundError:
        return idx
    for p in [x.strip() for x in text.split('\n\n') if x.strip()]:
        m = _HEAD.match(p)
        if not m:
            continue
        base = re.sub(r'[0-9]+$', '', m.group(1)).lower().strip('.')
        d = _clean_def(p[m.end():])
        if base not in idx and len(d) >= 10:
            idx[base] = d
    return idx


def _core_gloss(word):
    """Ядро: вернуть толкование из ref_lex_minimum.md, если найдено."""
    try:
        for line in open(CORE, encoding='utf-8'):
            m = re.match(r'^\| \d+ \| (\S+) \| \d+ \| .*? \| (.*?) \|$', line)
            if m and m.group(1).lower() == word:
                g = m.group(2).strip()
                return '' if g.startswith('—') else g
    except FileNotFoundError:
        pass
    return ''


def gloss(word):
    """Толкование слова ('' если не найдено)."""
    global _INDEX
    if _INDEX is None:
        _INDEX = _build_index()
    w = word.strip().lower()
    if not w or not re.search(r'[а-яё]', w):
        return ''
    if w in _INDEX:
        return _INDEX[w]
    # попытка без конечного -ся / хвостов
    for cut in ('ся', 'сь'):
        if w.endswith(cut) and w[:-2] in _INDEX:
            return _INDEX[w[:-2]]
    return _core_gloss(w)


def is_known(word):
    return bool(gloss(word))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print('usage: python dict_lookup.py слово [слово ...]')
        sys.exit(1)
    for w in sys.argv[1:]:
        g = gloss(w)
        print(f'{w}: {g if g else "(не найдено)"}')
