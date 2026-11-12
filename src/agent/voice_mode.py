"""Neira's live voice mode switch (the Qt app's "Голос" button).

The app toggles between:
  - "on":  tts_model openai_tts -> the voice server (neira_voice_server.py, port 8090)
  - "off": tts_model none_tts -> text-only answers, the voice server stopped (frees VRAM)

Used by the WebSocket handler for the "set-voice-mode" message type.
"""

import asyncio
import re
import subprocess
import time
import urllib.request

from loguru import logger

from .tts.tts_factory import TTSFactory

CONF = r"D:\AI\Open-LLM-VTuber\conf.yaml"
VOICE_PORT = 8090
VOICE_PY = r"D:\AI\fastqwen\.venv\Scripts\python.exe"
VOICE_SRV = r"D:\AI\voices\server\neira_voice_server.py"
VOICE_CWD = r"D:\AI\voices\server"


def _pid_on_port(port: int):
    try:
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "TCP"], text=True, errors="replace"
        )
    except Exception:
        return None
    needle = f":{port}"
    for line in out.splitlines():
        if needle in line and "LISTENING" in line:
            parts = line.split()
            if parts:
                try:
                    return int(parts[-1])
                except ValueError:
                    pass
    return None


def _free_vram_mib() -> float:
    """Free VRAM according to nvidia-smi (MiB), or -1 if unknown."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            text=True,
            errors="replace",
        )
        return float(out.strip().splitlines()[0])
    except Exception:
        return -1.0


def _stop_voice_server() -> str:
    pid = _pid_on_port(VOICE_PORT)
    if not pid:
        return "stopped-already"
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    except Exception as e:
        logger.warning(f"voice_mode: taskkill failed: {e}")
    deadline = time.time() + 15
    while time.time() < deadline:
        if _pid_on_port(VOICE_PORT) is None:
            return "stopped"
        time.sleep(1)
    return "stop-timeout"


def _voice_healthy() -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{VOICE_PORT}/health", timeout=2
        ):
            return True
    except Exception:
        return False


def _start_voice_server() -> str:
    if _pid_on_port(VOICE_PORT):
        return "already-running"
    try:
        CREATE_NO_WINDOW = 0x08000000
        with open(r"D:\AI\_tmp\voice_srv_autostart.log", "w", encoding="utf-8") as fo, \
             open(r"D:\AI\_tmp\voice_srv_autostart_err.log", "w", encoding="utf-8") as fe:
            subprocess.Popen(
                [VOICE_PY, "-I", VOICE_SRV, str(VOICE_PORT)],
                stdout=fo,
                stderr=fe,
                creationflags=CREATE_NO_WINDOW,
                cwd=VOICE_CWD,
            )
    except Exception as e:
        logger.error(f"voice_mode: start failed: {e}")
        return "start-error"
    deadline = time.time() + 300
    while time.time() < deadline:
        if _voice_healthy():
            return "started"
        time.sleep(3)
    return "start-timeout"


def _switch_conf(mode: str) -> None:
    with open(CONF, encoding="utf-8") as f:
        text = f.read()
    want = "none_tts" if mode == "off" else "openai_tts"
    new_text = re.sub(
        r"tts_model:\s*'?[a-z_]+'?", f"tts_model: '{want}'", text, count=1
    )
    if mode == "off":
        if not re.search(r"^none_tts:", new_text, flags=re.M):
            new_text += "\nnone_tts: {}\n"
    else:
        new_text = re.sub(r"\n?^none_tts:\s*\{\}\s*$", "", new_text, flags=re.M)
    with open(CONF, "w", encoding="utf-8") as f:
        f.write(new_text)


def _sync_session(default_context, session_context, target: str) -> None:
    """A long-lived client connection keeps its own context: copy the engine over."""
    if session_context is None:
        return
    scfg = getattr(session_context.character_config, "tts_config", None)
    if scfg is not None:
        scfg.tts_model = target
    session_context.tts_engine = default_context.tts_engine


async def set_voice_mode(default_context, session_context, mode: str) -> dict:
    """Switch Neira's voice mode. Returns a status dict for the client."""
    if mode not in ("on", "off"):
        return {"ok": False, "error": f"unknown mode: {mode}"}

    tts_config = getattr(default_context.character_config, "tts_config", None)
    current = getattr(tts_config, "tts_model", None) if tts_config else None
    # Fast path: the requested state is already fully in place (config + server)
    if mode == "on" and current == "openai_tts" and _pid_on_port(VOICE_PORT):
        _sync_session(default_context, session_context, "openai_tts")
        return {"ok": True, "mode": "on", "server": "already-on"}
    if mode == "off" and current == "none_tts" and _pid_on_port(VOICE_PORT) is None:
        _sync_session(default_context, session_context, "none_tts")
        return {"ok": True, "mode": "off", "server": "already-off"}

    # 1) build the new engine
    prev_target = current
    if mode == "off":
        engine = TTSFactory.get_tts_engine("none_tts")
    else:
        cfg = getattr(tts_config, "openai_tts", None)
        engine = (
            TTSFactory.get_tts_engine("openai_tts", **cfg.model_dump())
            if cfg
            else None
        )
        if engine is None:
            return {"ok": False, "error": "openai_tts config missing"}

    # 2) swap engines: the default cache (all future sessions) and the current session
    target = "none_tts" if mode == "off" else "openai_tts"
    if tts_config is not None:
        tts_config.tts_model = target
    default_context.tts_engine = engine
    if session_context is not None:
        scfg = getattr(session_context.character_config, "tts_config", None)
        if scfg is not None:
            scfg.tts_model = target
        session_context.tts_engine = engine

    # 3) start / stop the voice server
    if mode == "off":
        server = await asyncio.to_thread(_stop_voice_server)
    else:
        # Instant feedback instead of a 300s silent wait: the voice needs ~3.2 GB
        # VRAM, so if there is not enough free VRAM (e.g. a game or the browser is
        # using the GPU), say so right away.
        free_vram = await asyncio.to_thread(_free_vram_mib)
        if free_vram >= 0 and free_vram < 3500:
            # roll back the engine swap done in step 2
            if tts_config is not None:
                tts_config.tts_model = prev_target
            if session_context is not None:
                scfg = getattr(session_context.character_config, "tts_config", None)
                if scfg is not None:
                    scfg.tts_model = prev_target
            logger.warning(
                f"voice_mode: not enough free VRAM for the voice ({free_vram:.0f} MiB < 3500), rolled back"
            )
            return {
                "ok": False,
                "error": (
                    f"не хватает видеопамяти для голоса (свободно {free_vram:.0f} МБ, "
                    "нужно ~3500). Закройте игры и лишние программы."
                ),
            }
        server = await asyncio.to_thread(_start_voice_server)

    # 4) if the voice server failed to come up, roll everything back so the
    #    config never claims "voice on" while there is no voice
    if mode == "on" and server not in ("started", "already-running", "already-on"):
        if tts_config is not None:
            tts_config.tts_model = prev_target
        if session_context is not None:
            scfg = getattr(session_context.character_config, "tts_config", None)
            if scfg is not None:
                scfg.tts_model = prev_target
        await asyncio.to_thread(_switch_conf, "off" if prev_target == "none_tts" else "on")
        logger.warning(f"voice_mode: voice server did not start ({server}), rolled back to {prev_target}")
        return {"ok": False, "error": f"voice server did not start: {server}"}

    # 5) persist to conf.yaml so the next start keeps the mode
    await asyncio.to_thread(_switch_conf, mode)
    logger.info(f"Neira voice mode -> {target} (server: {server})")

    return {"ok": True, "mode": target, "server": server}
