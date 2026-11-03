# -*- coding: utf-8 -*-
"""Превращает пары ASCII-кавычек в толкованиях в « »."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\AI\neira-tools\knowledge\russkiy\ref_lex_minimum.md'
lines = open(P, encoding='utf-8').read().splitlines()
out = []
fixed = 0
for l in lines:
    if l.startswith('|') and '| № |' not in l:
        parts = l.split('|')  # [0]='', потом 5 колонок, [6]=''
        if len(parts) == 7:
            gloss = parts[5]
            if gloss.count('"') % 2 == 0 and gloss.count('"'):
                chunks = gloss.split('"')
                buf = chunks[0]
                for i, x in enumerate(chunks[1:], 1):
                    buf += ('«' if i % 2 == 1 else '»') + x
                parts[5] = buf
                fixed += 1
            parts[0] = ''
            l = '|'.join(parts)
    out.append(l)
open(P, 'w', encoding='utf-8').write('\n'.join(out))
print('gloss lines fixed:', fixed)
