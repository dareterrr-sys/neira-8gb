# -*- coding: utf-8 -*-
"""Добирает '—' в ref_lex_minimum.md из Викисловаря (action=parse)."""
import sys, re, json, urllib.parse, urllib.request, time
sys.stdout.reconfigure(encoding='utf-8')
CORE = r'D:\AI\neira-tools\knowledge\russkiy\ref_lex_minimum.md'
JUNK_END = ('ый', 'ая', 'ое', 'ые', 'ых', 'ым', 'ими', 'ами', 'ями', 'ние', 'ния', 'нии', 'ться', 'тся', 'ной', 'ному', 'ным', 'ью', 'его', 'ому')

def junk(w):
    return w.endswith(JUNK_END) or len(w) <= 3

lines = open(CORE, encoding='utf-8').read().splitlines()
missing = []
for i, l in enumerate(lines):
    if l.endswith('— (в словаре Ожегова не найдено) |'):
        m = re.match(r'^\| \d+ \| (\S+) \|', l)
        if m:
            missing.append((i, m.group(1).lower()))
need = [(i, w) for i, w in missing if not junk(w)]
print('need:', len(need))

def _strip_wikitext(s):
    s = re.sub(r'\{\{.*?\}\}', '', s, flags=re.S)
    s = re.sub(r'\[\[([^|\]]*?)\]\]', r'\1', s)
    s = re.sub(r"'''''?|'''?", '', s)
    s = s.replace('&#32;', ' ').replace('&#160;', ' ').replace('&#91;', '[').replace('&#93;', ']')
    # остатки шаблонов/ссылок
    s = re.sub(r'[\[\]{}|]', ' ', s)
    s = re.sub(r'[«»“”]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    s = s.strip(' .:,;-')
    return s


def fetch_one(title):
    q = urllib.parse.urlencode({
        'action': 'parse', 'page': title, 'prop': 'wikitext',
        'format': 'json', 'formatversion': '2', 'redirects': '1'})
    url = 'https://ru.wiktionary.org/w/api.php?' + q
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'NeiraLocalStudy/0.1'})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(12)
                continue
            raise
    wt = data.get('parse', {}).get('wikitext', '')
    # секция «Значение» (или «Семантические свойства»)
    m = re.search(r'===\s*Значение\s*===', wt)
    if not m:
        m = re.search(r'===\s*Семантические свойства\s*===', wt)
    if not m:
        return ''
    block = wt[m.end():]
    # до следующего заголовка/подзаголовка
    block = re.split(r'^==+[^=\n]+==+', block, flags=re.M)[0]
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith('#'):
            continue
        text = _strip_wikitext(line[1:].strip())
        if len(text) >= 25 and '.' in text:
            return text[:300]
    return ''

results = {}
for k, (i, w) in enumerate(need):
    try:
        p = fetch_one(w)
    except Exception as e:
        p = ''
        print('err', w, repr(e))
    if p and not p.lower().startswith('см.') and not p.startswith('('):
        results[w] = p
    time.sleep(3.5)

filled = 0
for i, w in need:
    if w in results:
        lines[i] = lines[i][:-len('— (в словаре Ожегова не найдено) |')] + results[w] + ' |'
        filled += 1
open(CORE, 'w', encoding='utf-8').write('\n'.join(lines))
print('filled from Wiktionary:', filled, 'of', len(need))
