"""What in the council earns its keep (29.10, the author: "we replaced it with tools almost entirely - rethink it").
Offline, from saved runs: for every question, was each specialist right, did the red critic / step judge object,
did the deep thinker run and was it right, was the final right. Then: how often would a simpler council get it.
Usage: python council_ablate.py runs/council_v310_mgsm.json [more runs]"""
import collections
import json
import sys

import eval_brain


def ok(item, a):
    return bool(a) and eval_brain.correct(item, a, a)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for path in sys.argv[1:]:
        rows = json.load(open(path, encoding="utf-8"))
        c = collections.Counter()
        for r in rows:
            info = r.get("info") or {}
            sp = info.get("specialists") or {}
            if not sp:
                c["no_info"] += 1
                continue
            right = {n: ok(r, a) for n, (a, _) in sp.items()}
            c["n"] += 1
            c["final_ok"] += r["ok"]
            for n, v in right.items():
                c["spec_ok_" + n] += v
            c["majority_ok"] += sum(right.values()) >= 2
            c["any_ok"] += any(right.values())
            fast_agree = info.get("agree") is not None and not info.get("pause")
            if info.get("pause"):
                c["deep_ran"] += 1
                d = (info.get("deep") or ["", ""])[0]
                c["deep_ok"] += ok(r, d)
                c["deep_fixed_majority_wrong"] += ok(r, d) and sum(right.values()) < 2
                c["deep_broke_majority_right"] += (not ok(r, d)) and sum(right.values()) >= 2
                if info.get("red_objects"):
                    c["sent_by_red"] += 1
                    c["red_send_helped"] += ok(r, d) and not right.get("логик", False)
                if info.get("steps_objects"):
                    c["sent_by_steps"] += 1
                    c["steps_send_helped"] += ok(r, d) and not ok(r, info.get("conclusion", ""))
            else:
                c["fast_final"] += 1
                c["fast_final_ok"] += r["ok"]
            # the final words vs the conclusion (Neira's mouth)
            concl_ok = ok(r, info.get("conclusion", ""))
            c["conclusion_ok"] += concl_ok
            c["mouth_broke"] += concl_ok and not r["ok"]
        n = c["n"] or 1
        print(f"== {path}: {c['n']} questions ({c['no_info']} without info)")
        print(f"   final {c['final_ok']}/{n}, conclusion {c['conclusion_ok']}, mouth broke {c['mouth_broke']}")
        print("   specialists alone: " + ", ".join(f"{k[8:]} {v}" for k, v in c.items() if k.startswith("spec_ok_")) +
              f"; majority {c['majority_ok']}; any {c['any_ok']}")
        print(f"   fast path {c['fast_final']} ({c['fast_final_ok']} right); deep ran {c['deep_ran']}: right "
              f"{c['deep_ok']}, fixed a wrong majority {c['deep_fixed_majority_wrong']}, broke a right majority "
              f"{c['deep_broke_majority_right']}")
        print(f"   sent by red critic {c['sent_by_red']} (logician was wrong and thinker right: {c['red_send_helped']}); "
              f"sent by step judge {c['sent_by_steps']} (helped {c['steps_send_helped']})")
        print(f"   mean time {sum(r.get('s', 0) for r in rows) / max(len(rows), 1):.1f} s")


if __name__ == "__main__":
    main()
