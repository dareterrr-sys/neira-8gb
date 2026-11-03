# -*- coding: utf-8 -*-
import sys, re
sys.stdout.reconfigure(encoding='utf-8')
text = open(r'D:\AI\neira-tools\knowledge\russkiy\dict_ozhegov.txt', encoding='utf-8', errors='ignore').read()
head_re = re.compile(r'^([А-ЯЁ][А-ЯЁ0-9]*(?:\.\.\.)?)\s*[, ]')
deriv = re.compile(r'\s+(?:II|11|2)\s+(?:прил\.?|сущ\.?|нареч\.?|межд\.?|союз|частиц)')
entries = {}
for p in [x.strip() for x in text.split('\n\n') if x.strip()]:
    m = head_re.match(p)
    if not m:
        continue
    base = re.sub(r'[0-9]+$', '', m.group(1)).lower().strip('.')
    d = deriv.split(p[m.end():], 1)[0]
    d = re.sub(r'\s+', ' ', d).strip().rstrip(' .,;:-')[:320]
    if base not in entries and len(d) >= 10:
        entries[base] = d
lines = open(r'D:\AI\neira-tools\knowledge\russkiy\ref_lex_minimum.md', encoding='utf-8').read().splitlines()
total = ozh = wikt = 0
miss = []
for l in lines:
    m = re.match(r'^\| \d+ \| (\S+) \| \d+ \| .*? \| (.*?) \|$', l)
    if not m:
        continue
    total += 1
    g = m.group(2)
    if g.startswith('—'):
        miss.append(m.group(1))
    elif entries.get(m.group(1).lower()) == g:
        ozh += 1
    else:
        wikt += 1
print('total', total, '| ozhegov', ozh, '| wiktionary', wikt, '| missing', len(miss))
print('missing:', miss)
