"""Rule-made training sentences for the punctuation net, where EGE tasks 16 and 18 fail (27.10 error check):
  intro  - an introductory word or phrase (Rosenthal's list, unambiguous ones only) put into a real sentence with commas
           on both sides: «Лишь отдельные листочки, по-видимому, качнутся…»;
  voc    - an address at the start or the end: «Таня, что с тобой?»;
  rep    - homogeneous members with repeated or paired conjunctions: «и A, и B, и C», «ни A, ни B», «как A, так и B»,
           «не только A, но и B», «то A, то B», and the comma-free ones «A и B», «ни свет ни заря»-type idioms.
Real sentences come from data/norm_texts.jsonl (FIPI texts) or data/classics.jsonl.
Out: data/aug.jsonl {"kind", "s"}. Usage: python aug_punct.py [n_per_kind=3000]
"""
import json
import os
import random
import re
import sys

import pymorphy3

HERE = os.path.dirname(os.path.abspath(__file__))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
random.seed(7)
M = pymorphy3.MorphAnalyzer()

INTRO = ["конечно", "кажется", "по-видимому", "видимо", "наверное", "к счастью", "к сожалению", "во-первых",
         "во-вторых", "может быть", "разумеется", "безусловно", "несомненно", "очевидно", "вероятно", "по-моему",
         "например", "кстати", "как известно", "как говорится", "по мнению учёных", "по словам автора",
         "на мой взгляд", "без сомнения", "в самом деле", "к удивлению", "между прочим", "одним словом",
         "по-видимому", "как ни странно", "к несчастью", "по правде говоря", "по крайней мере", "в частности",
         "как мне кажется", "как считают лингвисты", "по преданию", "должно быть", "стало быть", "пожалуй"]
VOC = ["Таня", "Иван Петрович", "друг мой", "мама", "ребята", "дорогой читатель", "товарищи", "Джим", "милая",
       "Анна Сергеевна", "сынок", "братцы", "господа", "Петя", "доктор", "дедушка", "Маша", "уважаемые коллеги",
       "мой друг", "старик", "дружище", "Оленька", "сударыня", "Николай Иванович"]
IDIOMS = ["ни свет ни заря", "ни жив ни мёртв", "ни слуху ни духу", "ни рыба ни мясо", "ни то ни сё",
          "ни дать ни взять", "ни больше ни меньше", "ни шатко ни валко", "и смех и грех", "и так и сяк",
          "и день и ночь", "ни туда ни сюда", "ни взад ни вперёд", "ни за что ни про что", "ни конца ни края",
          "ни пуха ни пера", "ни встать ни сесть", "ни много ни мало"]
NOUNS = ["музыка", "живопись", "театр", "книга", "история", "природа", "поэзия", "математика", "песня", "лес",
         "море", "город", "работа", "спорт", "шахматы", "кино", "архитектура", "физика", "сад", "дорога", "река"]
SUBJ_VERB = [("Мы", "любили"), ("Они", "изучали"), ("Дети", "рисовали"), ("Гости", "обсуждали"),
             ("Ученики", "вспоминали"), ("Старики", "хвалили"), ("Друзья", "видели"), ("Студенты", "читали о")]
ADJ = ["смешной", "поучительный", "актуальный", "интересный", "длинный", "трудный", "весёлый", "грустный",
       "тёплый", "светлый", "простой", "честный"]


def form(word, case):
    p = M.parse(word)[0]
    f = p.inflect({case})
    return f.word if f else word


def pool():
    for name in ("norm_texts.jsonl", "classics.jsonl"):
        path = os.path.join(HERE, "data", name)
        if os.path.exists(path):
            return [json.loads(l)["s"] for l in open(path, encoding="utf-8")]
    raise SystemExit("нет data/norm_texts.jsonl и data/classics.jsonl")


def intro(s):
    # before the predicate only (a finite verb not right after a preposition or conjunction): random places put it
    # inside phrases («Дочке в, может быть, стакан»)
    words = s.split(" ")
    ok = []
    for i in range(1, len(words)):
        prev, w = words[i - 1], words[i]
        if not (re.fullmatch(r"[а-яёА-ЯЁ-]+", prev) and re.fullmatch(r"[а-яё]+", w)):
            continue
        if "VERB" in M.parse(w)[0].tag and not ({"PREP", "CONJ", "PRCL"} & set(str(M.parse(prev.lower())[0].tag).replace(",", " ").split())):
            ok.append(i)
    if not ok or random.random() < 0.2:
        x = random.choice(INTRO)
        return x[0].upper() + x[1:] + ", " + s[0].lower() + s[1:]
    i = random.choice(ok)
    return " ".join(words[:i]) + ", " + random.choice(INTRO) + ", " + " ".join(words[i:])


def voc(s):
    v = random.choice(VOC)
    if random.random() < 0.5:
        return v[0].upper() + v[1:] + ", " + s[0].lower() + s[1:]
    return s[:-1] + ", " + v + s[-1]


def rep():
    subj, verb = random.choice(SUBJ_VERB)
    case = "loct" if verb.endswith(" о") else "accs"
    a, b, c = (form(x, case) for x in random.sample(NOUNS, 3))
    adj = random.sample(ADJ, 3)
    pats = [f"{subj} {verb} и {a}, и {b}, и {c}.", f"{subj} {verb} и {a}, и {b}.", f"{subj} {verb} ни {a}, ни {b}.",
            f"{subj} {verb} как {a}, так и {b}.", f"{subj} {verb} не только {a}, но и {b}.",
            f"{subj} {verb} то {a}, то {b}.", f"{subj} {verb} {a} и {b}.", f"{subj} {verb} {a}, {b} и {c}.",
            f"Спектакль оказался {form(adj[0], 'ablt')} и {form(adj[1], 'ablt')}.",
            f"Спектакль оказался и {form(adj[0], 'ablt')}, и {form(adj[1], 'ablt')}, и {form(adj[2], 'ablt')}.",
            f"Всё было {random.choice(IDIOMS)}.", f"Он вернулся домой {random.choice(IDIOMS)}.",
            f"Говорят, что дело шло {random.choice(IDIOMS)}."]
    return random.choice(pats)


def main():
    src = [s for s in pool() if s[-1] in ".!?" and 5 <= len(s.split()) <= 30]
    rows = [{"kind": "intro", "s": intro(random.choice(src))} for _ in range(N)]
    rows += [{"kind": "voc", "s": voc(random.choice(src))} for _ in range(N)]
    rows += [{"kind": "rep", "s": rep()} for _ in range(N)]
    random.shuffle(rows)
    with open(os.path.join(HERE, "data", "aug.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for k in ("intro", "voc", "rep"):
        print(k, [r["s"] for r in rows if r["kind"] == k][:3])


if __name__ == "__main__":
    main()
