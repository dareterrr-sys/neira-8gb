"""Smooth her melody after synthesis (29.10, the author: "smoothness is the whole point"). WORLD vocoder: the words and
timbre (spectral envelope, aperiodicity) stay, only the pitch curve is low-pass filtered - jumps flattened into glides,
the overall rise and fall kept. Usage: python smooth_world.py in.wav [strength_ms ...] -> in_smooth<ms>.wav"""
import os
import sys

import numpy as np
import pyworld as pw
import soundfile as sf
from scipy.ndimage import gaussian_filter1d

path = sys.argv[1]
strengths = [int(a) for a in sys.argv[2:]] or [40, 80]
w, sr = sf.read(path, dtype="float64")
w = w.mean(1) if w.ndim > 1 else w
FP = 5.0   # ms per WORLD frame
f0, t = pw.harvest(w, sr, frame_period=FP)
sp = pw.cheaptrick(w, f0, t, sr)
ap = pw.d4c(w, f0, t, sr)
voiced = f0 > 0
st = np.where(voiced, 12 * np.log2(np.where(voiced, f0, 1) / np.median(f0[voiced])), np.nan)
idx = np.arange(len(st))
filled = np.interp(idx, idx[voiced], st[voiced])   # bridge the unvoiced gaps so the curve glides across consonants
for ms in strengths:
    sm = gaussian_filter1d(filled, sigma=ms / FP)
    new = np.where(voiced, np.median(f0[voiced]) * 2 ** (sm / 12), 0.0)
    y = pw.synthesize(new, sp, ap, sr, frame_period=FP)
    y = y / max(1.0, np.abs(y).max())
    out = os.path.splitext(path)[0] + f"_smooth{ms}.wav"
    sf.write(out, y.astype(np.float32), sr)
    print(out)
