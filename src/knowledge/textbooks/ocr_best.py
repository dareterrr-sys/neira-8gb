"""A second, accurate reading of one scanned book (31.10, the author: «учебник должен быть идеальным»): Tesseract with
the tessdata_best Russian model (15 MB; the first reading used the fast 3.8 MB one), 300 dpi. The two readings are
merged word by word later (textbooks/merge_ocr.py). Resumable per page.
Usage (russkiy venv): python ocr_best.py <book.pdf> <out pages dir> [workers=4]"""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pypdfium2 as pdfium

TESS = r"D:\msys64\mingw64\bin\tesseract.exe"
BEST = r"D:\AI\models\tessdata_best"
PDF, OUT = sys.argv[1], sys.argv[2]
WORKERS = int(sys.argv[3]) if len(sys.argv) > 3 else 4


def read(png, out):
    r = subprocess.run([TESS, png, "stdout", "-l", "rus", "--tessdata-dir", BEST], capture_output=True)
    open(out, "w", encoding="utf-8").write(r.stdout.decode("utf-8", "replace"))
    os.remove(png)


def main():
    os.makedirs(OUT, exist_ok=True)
    d = pdfium.PdfDocument(PDF)
    with ThreadPoolExecutor(WORKERS) as ex:   # pdfium is not thread-safe: render here, read in parallel
        jobs = []
        for i in range(len(d)):
            out = os.path.join(OUT, f"{i + 1:04d}.txt")
            if os.path.exists(out):
                continue
            while sum(not j.done() for j in jobs) >= 2 * WORKERS:
                jobs[0].result() if not jobs[0].done() else jobs.pop(0)
            png = out[:-4] + ".png"
            d[i].render(scale=300 / 72, grayscale=True).to_pil().save(png)
            jobs.append(ex.submit(read, png, out))
        for j in jobs:
            j.result()
    print("готово", len(d), flush=True)


if __name__ == "__main__":
    main()
