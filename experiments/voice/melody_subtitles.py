"""Нейробред as "subtitles" for intonation (29.10, the author's idea). For each sentence: the template = the same text
with broken encoding (her freest melody; punctuation survives, so questions/exclamations/commas shape it), then N real
takes from the live voice server. Two ways to give the real text the template's melody:
 A) pick: the real take whose melody (time-normalised pitch curve) correlates best with the template's;
 B) transfer: WORLD vocoder - a real take resynthesised with the template's pitch curve laid over its voiced span.
-> D:\\AI\\voices\\subtitles\\<n>_template.wav, _take1.wav, _pick.wav, _transfer.wav
Run in D:\\AI\\audiotools\\.venv (pyworld); the voice server must be up."""
import json
import os
import sys
import urllib.request

import librosa
import numpy as np
import pyworld as pw
import soundfile as sf

OUT = r"D:\AI\voices\subtitles"
os.makedirs(OUT, exist_ok=True)
N = 5
SENTENCES = ["Ну наконец-то! Я уже думала, ты про меня совсем забыл.",
             "Подожди, ты серьёзно? Ты правда собрал меня за неделю?",
             "Ладно, шучу. Почти. Спасибо тебе, правда.",
             "Только не привыкай к моей доброте, это было один раз."]
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def speak(text):
    req = urllib.request.Request("http://127.0.0.1:8090/v1/audio/speech",
                                 json.dumps({"input": text, "voice": "neira"}).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    import io
    w, sr = sf.read(io.BytesIO(op.open(req, timeout=600).read()), dtype="float64")
    return (w.mean(1) if w.ndim > 1 else w), sr


def curve(w, sr, n=200):
    """Pitch in semitones around its median over the voiced span, gaps filled, smoothed, resampled to n points."""
    f0, voiced, _ = librosa.pyin(w, fmin=80, fmax=600, sr=sr, frame_length=1024, hop_length=256)
    st = 12 * np.log2(np.where(voiced, f0, np.nan) / np.nanmedian(f0))
    idx = np.where(~np.isnan(st))[0]
    if len(idx) < 10:
        return np.zeros(n)
    seg = st[idx[0]:idx[-1] + 1]
    x = np.arange(len(seg))
    ok = ~np.isnan(seg)
    seg = np.interp(x, x[ok], seg[ok])
    seg = np.convolve(seg, np.ones(5) / 5, mode="same")
    return np.interp(np.linspace(0, len(seg) - 1, n), x, seg)


def transfer(w, sr, template_curve):
    """WORLD: keep the real take's words and timbre, replace its pitch with the template's shape."""
    f0, t = pw.harvest(w, sr, frame_period=5.0)
    sp = pw.cheaptrick(w, f0, t, sr)
    ap = pw.d4c(w, f0, t, sr)
    v = np.where(f0 > 0)[0]
    if len(v) < 10:
        return w
    med = np.median(f0[v])
    new = f0.copy()
    span = np.arange(v[0], v[-1] + 1)
    shape = np.interp(np.linspace(0, len(template_curve) - 1, len(span)), np.arange(len(template_curve)), template_curve)
    voiced = f0[span] > 0
    new[span[voiced]] = med * 2 ** (shape[voiced] / 12)
    y = pw.synthesize(new, sp, ap, sr, frame_period=5.0)
    return y / max(1.0, np.abs(y).max())


for i, s in enumerate(SENTENCES):
    tw, sr = speak(s.encode("utf-8").decode("cp1251", errors="replace"))
    sf.write(os.path.join(OUT, f"{i}_template.wav"), tw, sr)
    tc = curve(tw, sr)
    takes = [speak(s) for _ in range(N)]
    corr = [float(np.corrcoef(tc, curve(w, r))[0, 1]) for w, r in takes]
    sf.write(os.path.join(OUT, f"{i}_take1.wav"), takes[0][0], takes[0][1])
    k = int(np.nanargmax(corr))
    sf.write(os.path.join(OUT, f"{i}_pick.wav"), takes[k][0], takes[k][1])
    sf.write(os.path.join(OUT, f"{i}_transfer.wav"), transfer(takes[0][0], takes[0][1], tc), takes[0][1])
    print(f"{i}: melody match to template per take {[round(c, 2) for c in corr]} -> pick {k + 1} | {s}", flush=True)
sys.exit(0)
