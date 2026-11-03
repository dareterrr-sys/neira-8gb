# -*- coding: utf-8 -*-
"""Строит ref_lex_minimum.md по корпусу учебников (частотность + лемматизация)."""
import os, re, sys, collections
sys.stdout.reconfigure(encoding='utf-8')
base = os.path.join('D:', os.sep, 'AI', 'Учебники по русскому языку', 'text')
import pymorphy3
morph = pymorphy3.MorphAnalyzer()

STOP = set("""и в не на я ты он она оно мы вы они это тот этот такая как так а но да или либо же бы ли у к от до по за из с о об при для против через между без под над про во со из-за из-под уже ещё ещё вот только только лишь даже тоже также здесь там тут сейчас теперь всегда иногда потом затем сначала опять вдруг очень совсем довольно почти слишком очень уж раз ну нет да ведь же вот значит например однако впрочем итак тоже потому поэтому оттого затем зачем почему откуда куда где когда какой какая какое какие какой чей чья чьё чьи который которая которое которые сколько столько сам сама само сами самый самая самое самые весь вся всё все весь каждый всякий любой иной другой иной некоторый некий несколько кто что ничто никто никого никому ничем ничем ничем нечего некого что-то кто-то что-нибудь кто-нибудь какой-то какой-нибудь чей-то кое-что кое-кто буду быть есть стал стала стало стали были был было была бывает будет будут будь давай можно надо нужно нельзя возможно должно следует хочется кажется видно слышно мочь мочь можете можно может могли могла могло могли бы""".split())

VOWELS = set('аеёиоуыэюя')
JUNK_END = ('ый', 'ая', 'ое', 'ые', 'ых', 'ым', 'ими', 'ами', 'ями', 'ние', 'ния', 'нии', 'ться', 'тся', 'ной', 'ному', 'ным', 'ью', 'его', 'ому')

def norm(w):
    p = morph.parse(w)[0]
    pos = p.tag.POS
    if pos in ('PREP', 'CONJ', 'PRCL', 'INTJ'):
        return None
    nf = p.normal_form
    if nf in STOP:
        return None
    if not any(ch in VOWELS for ch in nf):
        return None
    if len(nf) < 4 and len(nf) >= 2 and nf not in ('её',):
        return None
    return nf

texts = []
for fn in os.listdir(base):
    if fn.endswith('.txt'):
        try:
            with open(os.path.join(base, fn), encoding='utf-8', errors='ignore') as fh:
                texts.append(fh.read())
        except Exception:
            pass

cnt = collections.Counter()
samples = {}
for t in texts:
    for m in re.finditer(r'[а-яёА-ЯЁ]+', t):
        raw = m.group(0).lower()
        if len(raw) < 3:
            continue
        nf = norm(raw)
        if nf is None:
            continue
        cnt[nf] += 1
        if nf not in samples:
            s = t[max(0, m.start()-80):m.end()+80].replace('\n', ' ')
            s = re.sub(r'["”“„‟«»]', '', s)
            s = s.replace('|', '/')
            s = re.sub(r'\s+', ' ', s).strip()
            samples[nf] = s[:150]

def junk(nf, c):
    if c >= 200:
        return False
    return nf.endswith(JUNK_END) or len(nf) <= 3

top = [w for w, c in cnt.most_common() if not junk(w, c)][:1000]
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ref_lex_minimum.md')
with open(out, 'w', encoding='utf-8') as f:
    f.write('# Частотное ядро русской лексики\n\n')
    f.write('Источник: автоматический подсчёт частотности по корпусу OCR-текстов учебников в `D:\\AI\\Учебники по русскому языку\\text\\` (Розенталь, Лекант, Валгина, Баранов, Ладыженская и др.), лемматизация pymorphy3.\n\n')
    f.write('> Назначение: дать ядро словаря — слова, составляющие основу русского языка. К каждому слову приведён живой контекст из того же корпуса. Полные толкования значений следует брать из толкового словаря (следующий шаг).\n\n')
    f.write('## 1. Функциональные (служебные) слова\n\n')
    f.write(', '.join(sorted(STOP)) + '\n\n')
    f.write('## 2. Ядерная лексика (по частотности)\n\n')
    f.write('| № | слово | частота | контекст |\n|---|---|---|---|---|\n')
    for i, w in enumerate(top[:800], 1):
        f.write(f'| {i} | {w} | {cnt[w]} | {samples.get(w, "")} |\n')
print('OK', out, 'words', len(top))
