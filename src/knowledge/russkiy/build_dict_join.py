# -*- coding: utf-8 -*-
"""Парсит dict_ozhegov.txt (Ожегов-Шведова) и добавляет толкования в ref_lex_minimum.md."""
import re, sys, os
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
DICT = os.path.join(HERE, 'dict_ozhegov.txt')
CORE = os.path.join(HERE, 'ref_lex_minimum.md')

text = open(DICT, encoding='utf-8', errors='ignore').read()
paras = [p.strip() for p in text.split('\n\n') if p.strip()]
head_re = re.compile(r'^([А-ЯЁ][А-ЯЁ0-9]*(?:\.\.\.)?)\s*[, ]')
deriv = re.compile(r'\s+(?:II|11|2)\s+(?:прил\.?|сущ\.?|нареч\.?|межд\.?|союз|частиц|э\.?|устар\.?|разг\.?)')

def clean_def(s):
    s = deriv.split(s, 1)[0]
    s = re.sub(r'\s+', ' ', s).strip()
    if not s:
        return ''
    s = s.rstrip(' .,;:-')
    s = s.replace('|', '/')
    return s[:320]

entries = {}
for p in paras:
    m = head_re.match(p)
    if not m:
        continue
    hw = m.group(1)
    base = re.sub(r'[0-9]+$', '', hw).lower().strip('.')
    d = clean_def(p[m.end():])
    if base not in entries and len(d) >= 10:
        entries[base] = d

lines = open(CORE, encoding='utf-8').read().splitlines()
out = []
matched = 0
missing = []
for l in lines:
    m = re.match(r'^\| (\d+) \| (\S+) \| (\d+) \| (.*?) \|$', l)
    if m:
        w = m.group(2).lower()
        d = entries.get(w, '')
        if d:
            matched += 1
        else:
            missing.append(w)
        gloss = d if d else '— (в словаре Ожегова не найдено)'
        out.append(f'| {m.group(1)} | {m.group(2)} | {m.group(3)} | {m.group(4)} | {gloss} |')
    else:
        out.append(l)

# заменяем заголовок таблицы и вставляем новую колонку
for i, l in enumerate(out):
    if l.startswith('| № | слово | частота | контекст |'):
        out[i] = '| № | слово | частота | контекст | толкование (Ожегов-Шведова) |'
        out[i+1] = '|---|---|---|---|---|'
        break

header_note = ('> Толкования подключены из «Толкового словаря русского языка» С. И. Ожегова и Н. Ю. Шведовой '
               '(текст из открытого источника, локальный учебный файл `dict_ozhegov.txt`). '
               'Где слова нет в словаре, стоит «—».')
# добавить примечание после строки источника
for i, l in enumerate(out):
    if l.startswith('> Назначение:'):
        out.insert(i+1, header_note)
        break

open(CORE, 'w', encoding='utf-8').write('\n'.join(out))
print('matched', matched, 'of 800 core; missing', len(missing))
print('missing sample:', missing[:40])
