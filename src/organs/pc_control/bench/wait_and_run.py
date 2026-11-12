r"""Background orchestrator for stage 2. Waits, then:
 1) idle >= 300 s and no game: makes the 10 scenes (sends input) and repeats the pc_control live tests;
 2) GPU.lock absent and no game: takes GPU.lock, starts voice + brain with vision (variants), runs bench, stops what it started,
    removes its lock. Everything is logged to bench\data\orchestrator.log.
Run: .venv\Scripts\python.exe -u -m bench.wait_and_run"""
import os
import subprocess
import sys
import time
from pathlib import Path

from pc_control import idle
from . import bench as B
from .scenes import DATA, SCENES, game_running

LOCK = Path(r"D:\AI\neira-repo\docs\board\GPU.lock")
BRAIN_BAT = r"D:\AI\llama-neira-hot\brain-v40-live-vision.bat"
VOICE_BAT = r"D:\AI\voices\server\start-voice.bat"
LOG = DATA / "orchestrator.log"
ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
ME = "zrenie-upravlenie"


def log(*a):
    DATA.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def pid_on_port(port):
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    for ln in out.splitlines():
        if f":{port} " in ln and "LISTENING" in ln:
            return ln.split()[-1]


def lock_is_mine():
    try:
        return LOCK.read_text(encoding="utf-8", errors="replace").startswith(ME)
    except OSError:
        return False


DEADLINE = time.mktime(time.strptime(time.strftime("%Y-%m-%d") + " 11:30", "%Y-%m-%d %H:%M"))


def voice_ok():
    try:
        return B.S.get("http://127.0.0.1:8090/health", timeout=3).ok
    except Exception:
        return False


def brain_running():
    return "llama-server" in subprocess.run(["tasklist", "/FI", "IMAGENAME eq llama-server.exe"], capture_output=True, text=True).stdout.lower()


def kill_brain():
    subprocess.run(["taskkill", "/IM", "llama-server.exe", "/F"], capture_output=True)
    time.sleep(4)


def wait_health(timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if B.S.get("http://127.0.0.1:8080/health", timeout=3).ok:
                return True
        except Exception:
            pass
        if not subprocess.run(["tasklist", "/FI", "IMAGENAME eq llama-server.exe"], capture_output=True,
                              text=True).stdout.lower().count("llama-server"):
            return False                      # the process is gone: it refused the flags
        time.sleep(5)
    return False


def start_brain(tag, env_extra):
    env = {**os.environ, **env_extra}
    logf = open(Path(BRAIN_BAT).parent / f"brain_vision_{tag}.log", "w", encoding="utf-8")
    subprocess.Popen(["cmd", "/c", BRAIN_BAT], env=env, stdout=logf, stderr=subprocess.STDOUT)
    ok = wait_health(300)
    log(f"brain {tag} {env_extra}: {'READY' if ok else 'FAILED'}")
    return ok


def main():
    log("orchestrator started")
    scenes_ok = len(list(SCENES.glob("[0-9][0-9]_*.png"))) >= 8 if SCENES.exists() else False
    live_done = True   # done 10.11 06:03 (5 passed)
    while True:
        if game_running():
            time.sleep(60); continue
        if (not scenes_ok or not live_done) and idle.idle_seconds() >= idle.LIVE_MIN_IDLE:
            if not live_done:
                r = subprocess.run([PY, "-m", "pytest", "tests/test_live.py", "-rs", "-q"], cwd=ROOT, capture_output=True, text=True)
                log("live tests:", r.stdout[-600:]); live_done = True
            if not scenes_ok:
                r = subprocess.run([PY, "-m", "bench.scenes", "--auto"], cwd=ROOT, capture_output=True, text=True)
                log("scenes:", r.stdout[-1500:], r.stderr[-600:])
                scenes_ok = len(list(SCENES.glob("[0-9][0-9]_*.png"))) >= 10 or len(list(SCENES.glob("[0-9][0-9]_*.png"))) >= 8
            continue
        if scenes_ok and (not LOCK.exists() or lock_is_mine()) and not brain_running():
            break
        time.sleep(60)

    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if not lock_is_mine():
            return main()
        fd = None
    with (os.fdopen(fd, "w", encoding="utf-8") if fd is not None else open(os.devnull, "w")) as f:
        f.write(f"{ME}, задача 2 (зрение: замеры), начало {time.strftime('%d.%m.%Y %H:%M')}, ожидаемый конец +90 мин\n")
    log("GPU.lock taken")
    globals()["DEADLINE"] = time.time() + 70 * 60
    voice_started = os.environ.get("VOICE_MINE") == "1"
    try:
        if not B.port_listening(8090) and Path(VOICE_BAT).exists():
            vlog = open(DATA / "voice_start.log", "w")
            subprocess.Popen(["cmd", "/c", "call", VOICE_BAT], stdin=subprocess.DEVNULL, stdout=vlog, stderr=subprocess.STDOUT)
            t0 = time.time()
            while time.time() - t0 < 180 and not voice_ok():
                time.sleep(5)
            voice_started = True
            log("voice:", "READY" if voice_ok() else "TIMEOUT 180 s")
            if not voice_ok():
                raise RuntimeError("voice did not start in 180 s")
        kill_brain()
        variants = [("offload0", {"VISION_OFFLOAD": "0"}), ("offload1", {"VISION_OFFLOAD": "1"})]
        compat = []
        if os.environ.get("VARIANTS"):
            variants = [v for v in variants if v[0] in os.environ["VARIANTS"].split(",")]
        for tag, env in variants:
            ok = start_brain(tag, env)
            if not ok:                         # compatibility fallbacks (first variant only is enough to learn the key)
                kill_brain()
                for ctag, cenv in (("nodraft", {"NO_DRAFT": "1"}), ("noctx", {"NO_CTXSHIFT": "1"}),
                                   ("nodraft_noctx", {"NO_DRAFT": "1", "NO_CTXSHIFT": "1"})):
                    compat.append((tag, ctag))
                    if start_brain(f"{tag}_{ctag}", {**env, **cenv}):
                        tag = f"{tag}_{ctag}"; ok = True; break
                    kill_brain()
            if ok:
                left = DEADLINE - time.time()
                if left < 120:
                    log("deadline (70 min after lock) reached, stopping"); break
                try:
                    r = subprocess.run([PY, "-m", "bench.bench", "--tag", tag], cwd=ROOT, capture_output=True, text=True, timeout=left)
                    log(f"bench {tag}:", r.stdout[-2500:], r.stderr[-800:])
                except subprocess.TimeoutExpired:
                    log(f"bench {tag}: deadline (70 min after lock), partial results kept in data/results/{tag}")
            kill_brain()
    except Exception as e:
        log("ERROR:", repr(e))
    finally:
        kill_brain()
        if voice_started:
            p = pid_on_port(8090)
            if p:
                subprocess.run(["taskkill", "/PID", p, "/T", "/F"], capture_output=True)
        try:
            if LOCK.read_text(encoding="utf-8", errors="replace").startswith(ME):
                LOCK.unlink()
                log("GPU.lock removed")
        except OSError:
            pass
    log("done")


if __name__ == "__main__":
    sys.exit(main())
