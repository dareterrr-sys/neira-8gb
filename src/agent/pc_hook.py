"""Glue between the conversation pipeline / websocket and Neira's organ «Управление ПК»
(neira-tools/pc_control_organ.py, loaded in agent/agents/basic_memory_agent.py as PC_ORGAN; NEIRA_PC_CONTROL=0 = off).
v3, 10.11.2026, zrenie-upravlenie, stage 3."""
import asyncio
import json
from typing import Optional

from loguru import logger


def _agent_module():
    from .agent.agents import basic_memory_agent as b
    return b


def organ():
    try:
        return getattr(_agent_module(), "PC_ORGAN", None)
    except Exception:
        return None


def _sender(websocket_send):
    return lambda m: websocket_send(json.dumps(m))


class Turn:
    """What a user turn becomes: the text/images the agent sees; `history_text` is what goes to the chat history."""
    def __init__(self, text, images=None):
        self.text, self.images = text, images


NOTE_ENABLED = ("[Система: пользователь включил тебе управление компьютером; на экране красная рамка, клавиша Pause "
                "останавливает. Скажи одной-двумя фразами, что готова, и спроси, что сделать.]")
NOTE_DISABLED = "[Система: управление компьютером выключено. Скажи об этом одной фразой.]"
NOTE_REFUSED = "[Система: управление компьютером не включилось. Причина: {why}. Скажи об этом одной-двумя фразами.]"
NOTE_LOOK = "[Система: к сообщению приложен снимок экрана пользователя. Ответь по делу на его вопрос о нём.]"
NOTE_TASK = ("[Система: ты выполнила на компьютере пользователя его просьбу «{task}». Итог: {result} "
             "Расскажи об итоге своими словами, коротко. Говори только о действиях из списка «Реально выполненные действия»; "
             "ничего не добавляй (не говори, что что-то набрано, сохранено или отправлено, если этого нет в списке).]")


async def rewrite_turn(text: str, websocket_send, client_uid: str = "main") -> Optional[Turn]:
    """Called by process_single_conversation for every text or voice turn. None = an ordinary turn."""
    org = organ()
    if org is None or not isinstance(text, str):
        return None
    cmd = _agent_module().PC_CONTROL.parse_command(text, org.safety.enabled)
    if cmd is None:
        return None
    org.bind(_sender(websocket_send), asyncio.get_running_loop(), client_uid)
    kind = cmd[0]
    try:
        if kind == "enable":
            if org.safety.enabled:
                return Turn(NOTE_ENABLED)
            ok = await org.handle_enable()
            if ok:
                return Turn(NOTE_ENABLED)
            return Turn(NOTE_REFUSED.format(why=org.safety.stop_reason or "см. сообщение выше"))
        if kind == "disable":
            await org.handle_disable()
            return Turn(NOTE_DISABLED)
        if kind == "look":
            img = await asyncio.to_thread(org.snapshot_data)
            return Turn(text + "\n" + NOTE_LOOK, [img])
        if kind == "task":
            result = await org.run_task(cmd[1])
            return Turn(NOTE_TASK.format(task=cmd[1], result=result))
    except asyncio.CancelledError:
        org.safety.disable("прервано")
        raise
    except Exception as e:
        logger.exception(f"pc_control: {e}")
        return Turn(f"{text}\n[Система: управление компьютером дало сбой: {e}. Скажи об этом коротко.]")
    return None


# ---- websocket messages from Qt: pc-control-enable | pc-control-disable | pc-control-confirm {id, ok} ----

async def ws_enable(websocket, client_uid, data):
    org = organ()
    if org is None:
        await websocket.send_text(json.dumps({"type": "pc-control-status", "enabled": False,
                                              "reason": "орган управления не загружен"}))
        return
    org.bind(_sender(websocket.send_text), asyncio.get_running_loop(), client_uid)
    await org.handle_enable()


async def ws_disable(websocket, client_uid, data):
    org = organ()
    if org is None:
        return await ws_enable(websocket, client_uid, data)
    org.bind(_sender(websocket.send_text), asyncio.get_running_loop(), client_uid)
    await org.handle_disable()


async def ws_confirm(websocket, client_uid, data):
    org = organ()
    if org:
        org.handle_confirm(data.get("id"), bool(data.get("ok")))


async def announce(websocket, client_uid="main"):
    """On connect: tell Qt the organ exists (the button appears) and whether control is on."""
    org = organ()
    msg = {"type": "pc-control-status", "enabled": False, "reason": "орган управления не загружен"}
    if org is not None:
        org.bind(_sender(websocket.send_text), asyncio.get_running_loop(), client_uid)
        msg = {"type": "pc-control-status", "enabled": org.safety.enabled, "reason": ""}
    await websocket.send_text(json.dumps(msg))
