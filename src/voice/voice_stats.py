"""Characteristics of voice recordings (29.10): length, pitch (median, spread, range), smoothness (jumps > 1.2 st per
second of voice), pauses, loudness. Usage: python voice_stats.py a.wav b.wav ..."""
import os
import sys

import librosa
import numpy as np
import soundfile as sf

sys.stdout.reconfigure(encoding="utf-8")
print(f"{'file':28s} {'len s':>6s} {'Hz':>5s} {'spread st':>9s} {'range st':>8s} {'jumps/s':>7s} {'pauses %':>8s} "
      f"{'voice %':>7s} {'dB':>6s}")
for path in sys.argv[1:]:
    w, sr = sf.read(path, dtype="float32")
    w = w.mean(1) if w.ndim > 1 else w
    hop = 256
    f0, voiced, _ = librosa.pyin(w, fmin=80, fmax=600, sr=sr, frame_length=1024, hop_length=hop)
    f = f0[voiced & ~np.isnan(f0)]
    st = 12 * np.log2(np.where(voiced, f0, np.nan) / np.nanmedian(f0))
    d = np.abs(np.diff(st))
    both = ~np.isnan(st[1:]) & ~np.isnan(st[:-1])
    jumps = (d[both] > 1.2).sum() / (len(f) * hop / sr)
    rms = librosa.feature.rms(y=w, frame_length=1024, hop_length=hop)[0]
    silent = rms < 0.02 * rms.max()
    # pauses: silent runs longer than 0.15 s
    runs, cur = 0, 0
    for s in silent:
        cur = cur + 1 if s else 0
        if cur == int(0.15 * sr / hop):
            runs += 1
    pause_share = 100 * silent.mean()
    lo, hi = np.nanpercentile(st, [5, 95])
    print(f"{os.path.basename(path)[:28]:28s} {len(w) / sr:6.1f} {np.median(f):5.0f} {np.nanstd(st):9.2f} {hi - lo:8.1f} "
          f"{jumps:7.2f} {pause_share:8.1f} {100 * voiced.mean():7.1f} {20 * np.log10(np.sqrt(np.mean(w ** 2)) + 1e-9):6.1f}")
