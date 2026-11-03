"""The voice gives the GPU to the brain for a hard task (28.10, the author's idea: "Neira should warn that she needs to
think before the unload"). Brain (live mode, 3.2 GB) + voice (3.2 GB) + Windows and a game do not fit in 8 GB:
Windows pushes memory out to RAM and a long prompt is read at ~67 tokens/s instead of ~580. So on a hard turn Neira
first says she needs to think, the voice parks its weights in RAM once that sentence is spoken (POST /park, ~1.9 GB freed),
the specialists and the brain work alone on the GPU, and POST /unpark brings the voice back in ~0.1 s.
NEIRA_VOICE_SWAP=0 turns it off."""
import asyncio
import os
import random
import subprocess
import urllib.request

VOICE = os.environ.get("NEIRA_VOICE_URL", "http://127.0.0.1:8090")
START = r"D:\AI\voices\server\start-voice.bat"
LONG = 700   # characters: an EGE task with its text, a long puzzle
# each ends with "!": the sentence divider holds back a text ending in "." (it may grow into ". . .")
WARNINGS = ["[neutral] Хм, тут надо как следует подумать. Дай мне минутку, я сосредоточусь!",
            "[neutral] Так, это задачка посерьёзнее. Подожди немного, мне нужно подумать!",
            "[neutral] Секунду. Тут нужна вся моя голова, я подумаю и отвечу!"]


# said when an answer is not ready in NEIRA_WAIT_S (plan step 15); ready phrases too (phrases.json)
WAITS = ["[neutral] Хм, дай минутку, тут надо подумать!", "[neutral] Сейчас, ещё немного подумаю!"]


def waiting():
    return random.choice(WAITS)


def _get(path, timeout=2.0):
    try:
        return urllib.request.urlopen(VOICE + path, timeout=timeout).read().decode()
    except Exception:
        return ""


def voice_up():
    return _get("/health") == "ok"


def is_hard(text, russkiy=None):
    """A turn worth the swap: a long task or an EGE Russian one (the organ thinks for tens of seconds)."""
    if len(text) >= LONG:
        return True
    try:
        return bool(russkiy and russkiy.asks_russian(text))
    except Exception:
        return False


def warning():
    return random.choice(WARNINGS)


def _post(path, timeout=70.0):
    try:
        return urllib.request.urlopen(urllib.request.Request(VOICE + path, data=b"", method="POST"),
                                      timeout=timeout).read().decode()
    except Exception:
        return ""


async def unload(served_before, wait=300.0):
    """After the warning sentence was handed to the speech pipeline: wait until the server has taken it and spoken it
    (served count grew, nothing in flight), then park the voice in RAM (~1.9 GB of VRAM freed, back in ~0.1 s).
    -> True if parked."""
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    while loop.time() - t0 < wait:
        st = await asyncio.to_thread(_get, "/state")
        if not st:
            return False
        served, inflight = map(int, st.split())
        if served > served_before and inflight == 0:
            break
        await asyncio.sleep(0.2)
    return (await asyncio.to_thread(_post, "/park")).startswith("parked")


TIGHT_MIB = int(os.environ.get("NEIRA_TIGHT_MIB", "600"))


def free_vram():
    """Free VRAM in MiB as nvidia-smi sees it (games and other apps included; CUDA on Windows does not)."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return int(out.split()[0])
    except Exception:
        return 0


def tight():
    """Smart mode (29.10, the author's idea): park the voice for an ordinary turn only when the GPU is nearly full
    (a game, other apps); otherwise she speaks while the brain still writes (first word in ~3-5 s, not ~15)."""
    return free_vram() < TIGHT_MIB


async def park_now():
    """An ordinary turn in sequential mode: park as soon as nothing is being spoken (the server waits for that)."""
    return (await asyncio.to_thread(_post, "/park")).startswith("parked")


def served():
    st = _get("/state")
    return int(st.split()[0]) if st else 0


async def load(timeout=120.0):
    """Bring the parked voice back (~0.1 s; its first sentence captures the CUDA graphs again, ~1 s). If the server is
    gone, start it again as Neira-start does (~15-30 s)."""
    if await asyncio.to_thread(voice_up):
        return (await asyncio.to_thread(_post, "/unpark")).startswith("back")
    subprocess.Popen(["cmd.exe", "/c", "start", "Neira voice loader", "/MIN", "cmd", "/c", START],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    while loop.time() - t0 < timeout:
        if await asyncio.to_thread(voice_up):
            return True
        await asyncio.sleep(1.0)
    return False
