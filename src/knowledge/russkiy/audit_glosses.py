# -*- coding: utf-8 -*-
"""Аудит толкований: ок только проверенные (Ожегов, точное совпадение).
Сомнительные (шаблонные остатки, обрывы, транскрипции) -> '—'."""
import sys, re
sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\AI\neira-tools\knowledge\russkiy\ref_lex_minimum.md'

# Сбор эталона Ожегова (как в build_dict_join)
DICT = r'D:\AI\neira-tools\knowledge\russkiy\dict_ozhegov.txt'
head_re = re.compile(r'^([А-ЯЁ][А-ЯЁ0-9]*(?:\.\.\.)?)\s*[, ]')
deriv = re.compile(r'\s+(?:II|11|2)\s+(?:прил\.?|сущ\.?|нареч\.?|межд\.?|союз|частиц)')
entries = {}
for p in [x.strip() for x in open(DICT, encoding='utf-8', errors='ignore').read().split('\n\n') if x.strip()]:
    m = head_re.match(p)
    if not m:
        continue
    base = re.sub(r'[0-9]+$', '', m.group(1)).lower().strip('.')
    d = deriv.split(p[m.end():], 1)[0]
    d = re.sub(r'\s+', ' ', d).strip().rstrip(' .,;:-')[:320]
    if base not in entries and len(d) >= 10:
        entries[base] = d

BAD = re.compile(r'НКРЯ|источник=|}}|\{\{|\[\[|\]\]|\|/|//|дореформ|МФА|Зализняка|клитик|склонение|неодушевлённое|средний род|мужской род|женский род|Тихонов|&#\d+|&#91|&#93|&#160|&#32')

lines = open(P, encoding='utf-8').read().splitlines()
changed = 0
kept_wikt = 0
stats = {'total': 0, 'ozh': 0, 'wikt': 0, 'miss': 0}
out = []
for l in lines:
    m = re.match(r'^\| (\d+) \| (\S+) \| (\d+) \| (.*?) \| (.*?) \|$', l)
    if not m:
        out.append(l)
        continue
    stats['total'] += 1
    word, gloss = m.group(2).lower(), m.group(5)
    if gloss.startswith('—'):
        stats['miss'] += 1
        out.append(l)
        continue
    if entries.get(word) == gloss:
        stats['ozh'] += 1
        out.append(l)
        continue
    # Все не-Ожеговские толкования убираем: качество непредсказуемо (риск дезинформации).
    changed += 1
    gloss = '— (в словаре Ожегова не найдено)'
    out.append(f'| {m.group(1)} | {m.group(2)} | {m.group(3)} | {m.group(4)} | {gloss} |')

open(P, 'w', encoding='utf-8').write('\n'.join(out))
print('stats:', stats)
print('downgraded to —:', changed)
