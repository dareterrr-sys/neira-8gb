"""Scanned textbooks -> text Neira can read (31.10): every page rendered at 300 dpi and read by Tesseract (rus).
Out: <name>.txt next to a books dir's own text/ folder, pages marked «=== стр. N ===». Resumable per page
(text/<name>.pages/NNNN.txt), pages read in parallel.
Usage (russkiy venv: pypdfium2): python ocr_books.py <books dir> [workers=6] [file substring...]"""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pypdfium2 as pdfium

TESS = r"D:\msys64\mingw64\bin\tesseract.exe"
BOOKS = sys.argv[1]
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 6
ONLY = sys.argv[3:]
OUT = os.path.join(BOOKS, "text")


def has_text(path):
    d = pdfium.PdfDocument(path)
    n = min(len(d), 20)
    chars = sum(len(d[i].get_textpage().get_text_range().strip()) for i in range(n))
    return chars > 300 * n   # a real text layer, not a scan with a few stray letters


def read(png, out):
    r = subprocess.run([TESS, png, "stdout", "-l", "rus", "--psm", "3"], capture_output=True)
    open(out, "w", encoding="utf-8").write(r.stdout.decode("utf-8", "replace"))
    os.remove(png)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    for root, _, files in os.walk(BOOKS):
        if root.startswith(OUT):
            continue
        for f in sorted(files):
            if not f.lower().endswith(".pdf") or (ONLY and not any(s in f for s in ONLY)):
                continue
            path = os.path.join(root, f)
            name = os.path.splitext(f)[0]
            final = os.path.join(OUT, name + ".txt")
            if os.path.exists(final):
                continue
            d = pdfium.PdfDocument(path)
            n = len(d)
            if has_text(path):   # the text layer is there already: take it as is
                text = "\n".join(f"=== стр. {i + 1} ===\n" + d[i].get_textpage().get_text_range() for i in range(n))
                open(final, "w", encoding="utf-8").write(text)
                print(f"текст  {n:4} стр. {f}", flush=True)
                continue
            pages_dir = os.path.join(OUT, name + ".pages")
            os.makedirs(pages_dir, exist_ok=True)
            print(f"скан   {n:4} стр. {f} ...", flush=True)
            # pdfium is not thread-safe: pages are rendered here one by one, only Tesseract runs in parallel
            with ThreadPoolExecutor(WORKERS) as ex:
                jobs = []
                for i in range(n):
                    out = os.path.join(pages_dir, f"{i + 1:04d}.txt")
                    if os.path.exists(out):
                        continue
                    while sum(not j.done() for j in jobs) >= 2 * WORKERS:   # a few pages ahead, not 450 PNGs on disk
                        jobs[0].result() if not jobs[0].done() else jobs.pop(0)
                    png = out[:-4] + ".png"
                    d[i].render(scale=300 / 72, grayscale=True).to_pil().save(png)
                    jobs.append(ex.submit(read, png, out))
                for j in jobs:
                    j.result()
            text = "\n".join(f"=== стр. {i + 1} ===\n" + open(os.path.join(pages_dir, f"{i + 1:04d}.txt"),
                                                                 encoding="utf-8").read() for i in range(n))
            open(final, "w", encoding="utf-8").write(text)
            print(f"готово {n:4} стр. {f}", flush=True)


if __name__ == "__main__":
    main()
