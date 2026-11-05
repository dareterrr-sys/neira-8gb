"""Tables for the report: organ vs the author's ear (ear.json, goda.json) and the voice's error rate (voice_*.json).
Usage (any venv): python analyze.py runs_dir > report.txt"""
import collections
import json
import os
import sys

R = sys.argv[1]
out = open(os.path.join(R, "report.txt"), "w", encoding="utf-8")


def p(*a):
    print(*a, file=out)


def phrase_verdict(words):
    v = [w["verdict"] for w in words]
    if "неверно" in v:
        return "bad"
    if "верно" in v:
        return "good"
    return "unsure"


if os.path.exists(os.path.join(R, "goda.json")):
    p("== «года» (dev) ==")
    for r in json.load(open(os.path.join(R, "goda.json"), encoding="utf-8")):
        w = [x for x in r["words"] if x["word"] == "года"][0]
        p(f"{os.path.basename(r['wav'])}: орган {w['verdict']} ({w.get('heard_form')}, запас {w.get('q_margin')}) | ухо: {r['ear_goda']}")

if os.path.exists(os.path.join(R, "ear.json")):
    ear = json.load(open(os.path.join(R, "ear.json"), encoding="utf-8"))
    p("\n== ухо автора, фразы (stress_rate + stress_rate2) ==")
    tab = collections.Counter()
    for r in ear:
        tab[(r["ear"], phrase_verdict(r["words"]))] += 1
    for e in ("good", "bad"):
        n = sum(tab[(e, o)] for o in ("good", "bad", "unsure"))
        p(f"автор {e:4s} n={n}: орган good {tab[(e, 'good')]}, bad {tab[(e, 'bad')]}, не уверен {tab[(e, 'unsure')]}")
    dec = [(r["ear"], phrase_verdict(r["words"])) for r in ear if phrase_verdict(r["words"]) != "unsure"]
    agree = sum(a == b for a, b in dec)
    p(f"согласие там, где орган решил: {agree}/{len(dec)}")
    for rnd in ("stress1", "stress2"):
        sub = [r for r in ear if r["round"] == rnd]
        d = [(r["ear"], phrase_verdict(r["words"])) for r in sub if phrase_verdict(r["words"]) != "unsure"]
        p(f"  {rnd}: решено {len(d)}/{len(sub)}, согласие {sum(a == b for a, b in d)}/{len(d)}")
    # words
    wc = collections.Counter(w["verdict"] for r in ear for w in r["words"])
    p("слова (все 2+ слога):", dict(wc))
    # per-word view for the words with a norm (FIPI / morphology)
    p("\n-- слова с нормой (ФИПИ / морфология), ухо автора по фразе --")
    t2 = collections.Counter()
    for r in ear:
        for w in r["words"]:
            if w.get("expected") is not None:
                t2[(r["ear"], w["verdict"])] += 1
    for e in ("good", "bad"):
        p(f"  фраза {e}: " + ", ".join(f"{v} {t2[(e, v)]}" for v in ("верно", "неверно", "не уверен")))
    # misses to read by eye (lesson «ошибается проверяющий»)
    p("\n-- фразы автор good, орган bad (разобрать) --")
    for r in ear:
        if r["ear"] == "good" and phrase_verdict(r["words"]) == "bad":
            bad = [f"{w['word']}→{w.get('heard_form')} (надо {w.get('expected_form')}, {w['basis']}, {w.get('q_margin')})"
                   for w in r["words"] if w["verdict"] == "неверно"]
            p(f"  [{r['round']} {r['model']} s{r['sentence']}] {r['text']} :: " + "; ".join(bad))
    p("\n-- фразы автор bad, орган good/не уверен --")
    for r in ear:
        if r["ear"] == "bad" and phrase_verdict(r["words"]) != "bad":
            p(f"  [{r['round']} {r['model']} s{r['sentence']}] {r['text']} :: орган {phrase_verdict(r['words'])}")

for name in ("voice_fipi.json", "voice_interview.json"):
    f = os.path.join(R, name)
    if not os.path.exists(f):
        continue
    res = json.load(open(f, encoding="utf-8"))
    p(f"\n== {name}: частота ошибок голоса ==")
    c = collections.Counter()
    kinds = collections.defaultdict(collections.Counter)
    errs = []
    for r in res:
        for w in r["words"]:
            c[w["verdict"]] += 1
            kind = "ФИПИ" if w["why"].startswith("ФИПИ") else ("РАН" if w["why"].startswith("РАН (статья") else (
                "морфология" if w["why"].startswith("OpenCorpora") else "норма не задана"))
            kinds[kind][w["verdict"]] += 1
            if w["verdict"] == "неверно":
                errs.append(f"  {os.path.basename(os.path.dirname(r['wav']))}/{os.path.basename(r['wav'])}: "
                            f"{w['word']} → {w.get('heard_form')} (надо {w.get('expected_form')}; {w['why']}; "
                            f"{w['basis']}, запас {w.get('q_margin')})")
    p(f"фраз {len(res)}, проверено слов {sum(c.values())}: " + ", ".join(f"{k} {v}" for k, v in c.items()))
    withnorm = sum(any(w.get("expected") is not None for w in r["words"]) for r in res)
    p(f"фраз со словом с нормой (судья включится): {withnorm} из {len(res)}")
    for k, v in kinds.items():
        p(f"  {k}: " + ", ".join(f"{a} {b}" for a, b in v.items()))
    p("ошибки:")
    for e in errs:
        p(e)
out.close()
