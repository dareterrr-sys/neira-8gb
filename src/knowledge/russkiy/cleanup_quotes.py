# -*- coding: utf-8 -*-
"""Заменяет ASCII-кавычки " на « » в ref_lex_minimum.md (только чётные пары в строке)."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\AI\neira-tools\knowledge\russkiy\ref_lex_minimum.md'
lines = open(P, encoding='utf-8').read().splitlines()
out = []
fixed = 0
for l in lines:
    if l.count('"') % 2 == 0 and l.count('"'):
        parts = l.split('"')
        buf = parts[0]
        for i, x in enumerate(parts[1:], 1):
            buf += ('«' if i % 2 == 1 else '»') + x
        out.append(buf)
        fixed += 1
    else:
        out.append(l)
open(P, 'w', encoding='utf-8').write('\n'.join(out))
print('lines fixed:', fixed)
