# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\AI\neira-tools\knowledge\russkiy\ref_lex_minimum.md'
t = open(P, encoding='utf-8').read()
t2 = t.replace('"', '')
open(P, 'w', encoding='utf-8').write(t2)
print('removed:', t.count('"'))
