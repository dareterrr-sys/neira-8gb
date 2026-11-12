"""Server -> client signals for the Qt app (format fixed by the staff, 12.11.2026; do not change without them).

  {"type": "neira-stress", "level": <0..1>, "reason": "<short>"}   - overload level (0 calm, >= 0.7 overload)
  {"type": "neira-stats", "tok_s": <float>, "tokens": <int>, "ctx_tokens": <int>}  - real numbers from the
      llama-server `timings` of the last answer (not an estimate)
"""
import json
from typing import Optional

from loguru import logger


def stats_message(timings: Optional[dict]) -> Optional[dict]:
    """Build neira-stats from llama-server `timings`; None when there are no real numbers."""
    if not timings:
        return None
    try:
        tokens = int(timings.get("predicted_n") or 0)
        tok_s = float(timings.get("predicted_per_second") or 0.0)
        ctx = tokens + int(timings.get("prompt_n") or 0) + int(timings.get("cache_n") or 0)
    except (TypeError, ValueError):
        return None
    if tokens <= 0:
        return None
    return {"type": "neira-stats", "tok_s": round(tok_s, 2), "tokens": tokens, "ctx_tokens": ctx}


def stress_message(level: float, reason: str = "") -> dict:
    level = max(0.0, min(1.0, float(level)))
    return {"type": "neira-stress", "level": round(level, 3), "reason": str(reason)[:80]}


async def send_stats(websocket_send, llm) -> None:
    """After an answer: send neira-stats from the llm's last timings (if the llm has recorded them)."""
    msg = stats_message(getattr(llm, "last_timings", None))
    if msg is None:
        return
    await websocket_send(json.dumps(msg))
    logger.info(f"neira-stats sent: {msg}")


# ---- neira-stress: system load (staff decision 12.11.2026, variant 1) ----------------------------------------------
# NOTE: neira-tools/stress_organ is NOT used here - that organ checks WORD STRESS (ударение), it has nothing to do
# with overload. "Overload" = load of the system: level is the maximum of
#   free VRAM   (>= 1000 MiB -> 0, <= 300 MiB -> 1, linear between),
#   speed of the last answer (>= 20 tok/s -> 0, <= 8 tok/s -> 1, linear between),
#   a llama-server timeout / error of the turn -> 1 for this turn.
# Sent only when the level moved by >= 0.1 and not more often than once per 2 s; VRAM is measured (nvidia-smi) at most
# once per 5 s.
import asyncio
import subprocess
import time

VRAM_OK_MIB, VRAM_BAD_MIB = 1000.0, 300.0
SPEED_OK, SPEED_BAD = 20.0, 8.0
MIN_STEP, MIN_GAP_S, VRAM_EVERY_S = 0.1, 2.0, 5.0


def _ramp(x: float, ok: float, bad: float) -> float:
    """0 at `ok`, 1 at `bad`, linear between (works for ok > bad and ok < bad)."""
    return max(0.0, min(1.0, (x - ok) / (bad - ok)))


def stress_level(free_vram_mib: Optional[float], tok_s: Optional[float], failed: bool = False):
    """-> (level 0..1, reason) from the three sources; the biggest one wins."""
    parts = []
    if failed:
        parts.append((1.0, "ошибка или таймаут ответа"))
    if free_vram_mib is not None:
        parts.append((_ramp(free_vram_mib, VRAM_OK_MIB, VRAM_BAD_MIB), f"свободной VRAM {free_vram_mib:.0f} МиБ"))
    if tok_s:
        parts.append((_ramp(tok_s, SPEED_OK, SPEED_BAD), f"скорость {tok_s:.1f} ток/с"))
    if not parts:
        return 0.0, ""
    level, reason = max(parts, key=lambda p: p[0])
    return level, (reason if level > 0 else "")


def read_free_vram_mib() -> Optional[float]:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return min(float(x) for x in out.stdout.split())
    except Exception:
        return None


class StressMonitor:
    def __init__(self, read_vram=read_free_vram_mib, clock=time.monotonic):
        self._read_vram, self._clock = read_vram, clock
        self._vram_at, self._vram = -1e9, None
        self._sent_at, self.sent_level = -1e9, 0.0

    async def _free_vram(self) -> Optional[float]:
        if self._clock() - self._vram_at >= VRAM_EVERY_S:
            self._vram = await asyncio.to_thread(self._read_vram)
            self._vram_at = self._clock()
        return self._vram

    async def message(self, tok_s: Optional[float] = None, failed: bool = False) -> Optional[dict]:
        """The neira-stress message to send now, or None (level moved < 0.1, or sent less than 2 s ago)."""
        level, reason = stress_level(await self._free_vram(), tok_s, failed)
        now = self._clock()
        if abs(level - self.sent_level) < MIN_STEP or now - self._sent_at < MIN_GAP_S:
            return None
        self._sent_at, self.sent_level = now, level
        return stress_message(level, reason)


MONITOR = StressMonitor()


async def send_stress(websocket_send, llm=None, failed: bool = False) -> None:
    timings = getattr(llm, "last_timings", None) or {}
    tok_s = timings.get("predicted_per_second") if timings.get("predicted_n") else None
    msg = await MONITOR.message(tok_s, failed)
    if msg is not None:
        await websocket_send(json.dumps(msg))
        logger.info(f"neira-stress sent: {msg}")
