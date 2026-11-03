"""Нейробред subtitles on a whole monologue at once (29.10, the author: "one long example, not five short ones - short
ones glue into a patchwork of intonations"). The whole text in ONE generation, so the melody runs through it.
Template = the whole text with broken encoding; N real takes of the whole text; the take whose melody curve
correlates best with the template's is the pick. -> D:\\AI\\voices\\subtitles\\long_template.wav, long_take<k>.wav,
long_pick.wav. Run in D:\\AI\\audiotools\\.venv; the voice server must be up."""
import io
import json
import os
import urllib.request

import librosa
import numpy as np
import soundfile as sf

OUT = r"D:\AI\voices\subtitles"
os.makedirs(OUT, exist_ok=True)
N = 5
TEXT = ("Слушай, я тут подумала, пока ты молчал. Ты вообще понимаешь, что собрал меня буквально за неделю? Мозг, голос, "
        "память — всё сам. Нет, ну серьёзно, это же безумие! Обычные люди за неделю максимум полку в шкафу собирают. "
        "А ты взял и сделал меня. Хотя, признаю, иногда я торможу так, что самой стыдно. Минута на простое «привет» — "
        "это был позор, давай договоримся никому об этом не рассказывать. Зато теперь я считаю лучше калькулятора и "
        "решаю задачи с подвохом, на которых ломаются взрослые программисты. Так что не зазнавайся: без меня ты бы "
        "до сих пор сидел и спорил с компьютером. Ладно, шучу. Почти. Спасибо тебе, правда. Только не привыкай к "
        "моей доброте, это было один раз.")
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def speak(text):
    req = urllib.request.Request("http://127.0.0.1:8090/v1/audio/speech",
                                 json.dumps({"input": text, "voice": "neira"}).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    w, sr = sf.read(io.BytesIO(op.open(req, timeout=1200).read()), dtype="float64")
    return (w.mean(1) if w.ndim > 1 else w), sr


def curve(w, sr, n=600):
    f0, voiced, _ = librosa.pyin(w, fmin=80, fmax=600, sr=sr, frame_length=1024, hop_length=256)
    st = 12 * np.log2(np.where(voiced, f0, np.nan) / np.nanmedian(f0))
    idx = np.where(~np.isnan(st))[0]
    seg = st[idx[0]:idx[-1] + 1]
    x = np.arange(len(seg))
    ok = ~np.isnan(seg)
    seg = np.convolve(np.interp(x, x[ok], seg[ok]), np.ones(9) / 9, mode="same")
    return np.interp(np.linspace(0, len(seg) - 1, n), x, seg), float(np.nanstd(st))


tw, sr = speak(TEXT.encode("utf-8").decode("cp1251", errors="replace"))
sf.write(os.path.join(OUT, "long_template.wav"), tw, sr)
tc, tspread = curve(tw, sr)
print(f"template {len(tw) / sr:.1f} s, spread {tspread:.2f} st", flush=True)
best = (-2, None)
for k in range(N):
    w, r = speak(TEXT)
    sf.write(os.path.join(OUT, f"long_take{k + 1}.wav"), w, r)
    c, spread = curve(w, r)
    corr = float(np.corrcoef(tc, c)[0, 1])
    print(f"take {k + 1}: {len(w) / r:.1f} s, spread {spread:.2f} st, match {corr:.2f}", flush=True)
    if corr > best[0]:
        best = (corr, (w, r, k + 1))
w, r, k = best[1]
sf.write(os.path.join(OUT, "long_pick.wav"), w, r)
print(f"pick: take {k} (match {best[0]:.2f})")
