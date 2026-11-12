import json, sys
from pathlib import Path
R = Path(__file__).resolve().parent / "data" / "results" / sys.argv[1]
S = Path(__file__).resolve().parent / "data" / "scenes"
d = json.loads((R / "describe.json").read_text(encoding="utf-8"))
print("DESCRIBE recall per scene:")
for x in d:
    print(f"  {x['scene']}: {len(x['hit'])}/{len(x['facts'])}  {x['wall_s']:.0f}s")
rs = [x["recall"] for x in d if x["recall"] is not None]
print("  mean recall", round(sum(rs) / len(rs), 2))
sel = json.loads((R / "select.json").read_text(encoding="utf-8"))
print("SELECT:", sum(x["hit"] for x in sel), "/", len(sel), "mean s", round(sum(x["wall_s"] for x in sel) / len(sel), 1),
      "mean prompt tok", round(sum(x["prompt_tokens"] or 0 for x in sel) / len(sel)))
for x in sel:
    if not x["hit"]:
        print("  miss", x["scene"], x["target"], "want", x["want"], "got", x["got"], "of", x["n_elems"])
c = json.loads((R / "coords.json").read_text(encoding="utf-8"))
for size in (1024, 1280, 1600):
    for mode in ("norm", "px"):
        rr = [r[mode] for r in c if r["size"] == size]
        parsed = [r for r in rr if r.get("parsed")]
        err = sorted(r["err_px"] for r in parsed)
        print(f"COORDS {size} {mode}: {sum(r['hit'] for r in rr)}/{len(rr)} hits, parsed {len(parsed)}, median err px {round(err[len(err)//2]) if err else None}")
print("elements per scene:")
for p in sorted(S.glob("[0-9][0-9]_*.json")):
    m = json.loads(p.read_text(encoding="utf-8"))
    print(f"  {p.stem}: {len(m['elements'])} elems, {len(m['targets'])} targets")
