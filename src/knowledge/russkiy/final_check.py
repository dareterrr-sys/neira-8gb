# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\AI\neira-tools\knowledge\russkiy\ref_lex_minimum.md'
t = open(P, encoding='utf-8').read()
print('ascii-dquote:', t.count('"'))
lines = t.splitlines()
bad = 0
for l in lines:
    if l.startswith('|') and '| № |' not in l and len(l.split('|')) != 7:
        bad += 1
        print('BAD:', l[:100])
print('bad-col rows:', bad)
