"""Proofreading by the scan (31.10, the author: «в учебнике вообще не должно быть ошибок»): every word of the used
Rozental paragraphs the dictionary does not know is found on its page (Tesseract word boxes) and its line is cut out
of the scan with the word framed; the crops go into numbered sheets a person (or Claude) reads against the text.
Out: <out dir>/sheet_NN.png + items.json [{n, par, word, page, found}]
Usage (Open-LLM-VTuber venv; renders with the russkiy venv's pypdfium2 via a subprocess): python proof_crops.py <out dir>"""
import difflib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, r"D:\AI\neira-tools\knowledge")
import rozental  # noqa: E402

PDF = r"D:\AI\Учебники по русскому языку\добавлено_v2\rozental_d_e_spravochnik_po_russkomu_yazyku_prakticheskaya_s.pdf"
TESS = r"D:\msys64\mingw64\bin\tesseract.exe"
BEST = r"D:\AI\models\tessdata_best"
RUSSKIY_PY = r"D:\AI\neira-tools\russkiy\.venv\Scripts\python.exe"
OUT = sys.argv[1]


def pages_of(span, lines):
    pg, out = 0, set()
    for i, l in enumerate(lines):
        m = re.match(r"=== стр\. (\d+) ===", l)
        if m:
            pg = int(m.group(1))
        if span[0] <= i < span[1]:
            out.add(pg)
    first = max([int(m.group(1)) for l in lines[:span[0]] if (m := re.match(r"=== стр\. (\d+) ===", l))], default=1)
    return sorted(out | {first})


def main():
    os.makedirs(OUT, exist_ok=True)
    morph = rozental._morph()
    pars = rozental.paragraphs()
    lines = open(rozental.BOOK, encoding="utf-8").read().splitlines()
    refs = sorted({p for _, rs in rozental.ERRORS + rozental.MEANS for p, _ in rs if not isinstance(p, tuple)})
    todo = []
    for p in refs:
        text = "\n".join(pars[p][1])
        words = sorted({w for w in re.findall(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)?", text)
                        if len(w) > 2 and not w[0].isupper() and not morph.word_is_known(w.lower())})
        todo += [(p, w, pages_of(rozental.SPANS[p], lines)) for w in words]
    need = sorted({pg for _, _, pgs in todo for pg in pgs})
    # page images (300 dpi, as the OCR) and word boxes
    script = ("import pypdfium2 as p,sys\nd=p.PdfDocument(sys.argv[1])\nfor n in map(int,sys.argv[3:]):\n"
              " d[n-1].render(scale=300/72,grayscale=True).to_pil().save(f'{sys.argv[2]}/p{n:04d}.png')\n")
    missing = [pg for pg in need if not os.path.exists(f"{OUT}/p{pg:04d}.png")]
    if missing:
        subprocess.run([RUSSKIY_PY, "-I", "-c", script, PDF, OUT] + [str(x) for x in missing], check=True)
    boxes = {}
    for pg in need:
        tsv = f"{OUT}/p{pg:04d}.tsv"
        if not os.path.exists(tsv):
            # to stdout: this Tesseract build cannot write to a Cyrillic output path
            r = subprocess.run([TESS, f"{OUT}/p{pg:04d}.png", "stdout", "-l", "rus", "--tessdata-dir", BEST, "-c", "tessedit_create_tsv=1"],
                               capture_output=True, env=dict(os.environ, OMP_THREAD_LIMIT="2"))
            open(tsv, "w", encoding="utf-8").write(r.stdout.decode("utf-8", "replace"))
        rows = [r.split("\t") for r in open(tsv, encoding="utf-8").read().splitlines()[1:]]
        boxes[pg] = [(r[11], int(r[6]), int(r[7]), int(r[8]), int(r[9])) for r in rows if len(r) == 12 and r[11].strip()]
    from PIL import Image, ImageDraw
    crops, items = [], []
    for n, (p, w, pgs) in enumerate(todo, 1):
        part = w.split("-")[0].lower()
        best = max(((difflib.SequenceMatcher(None, part, re.sub(r"[^а-яё]", "", t.lower())).ratio(), pg, x, y, bw, bh)
                    for pg in pgs for t, x, y, bw, bh in boxes.get(pg, [])), default=None)
        items.append({"n": n, "par": p, "word": w, "page": best[1] if best else None,
                      "match": round(best[0], 2) if best else 0})
        if not best:
            continue
        _, pg, x, y, bw, bh = best
        im = Image.open(f"{OUT}/p{pg:04d}.png").convert("RGB")
        top, bot = max(0, y - int(bh * 0.6)), min(im.height, y + int(bh * 1.6))
        crop = im.crop((0, top, im.width, bot))
        ImageDraw.Draw(crop).rectangle((x - 4, y - top - 3, x + bw + 4, y - top + bh + 3), outline=(255, 0, 0), width=4)
        crops.append((n, w, crop.resize((1100, int(crop.height * 1100 / crop.width)))))
    for s in range(0, len(crops), 12):
        part = crops[s:s + 12]
        sheet = Image.new("RGB", (1100, sum(c.height + 34 for _, _, c in part)), "white")
        d, y = ImageDraw.Draw(sheet), 0
        from PIL import ImageFont
        font = ImageFont.truetype(r"C:\Windows\Fontsrial.ttf", 22)   # the default font has no Cyrillic
        for n, w, c in part:
            d.text((6, y + 4), f"#{n}  в тексте: {w}", fill=(0, 0, 200), font=font)
            sheet.paste(c, (0, y + 30))
            y += c.height + 34
        sheet.save(f"{OUT}/sheet_{s // 12 + 1:02d}.png")
    json.dump(items, open(f"{OUT}/items.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(len(items), "мест,", len(crops), "вырезок,", (len(crops) + 11) // 12, "листов; страниц", len(need))


if __name__ == "__main__":
    main()
