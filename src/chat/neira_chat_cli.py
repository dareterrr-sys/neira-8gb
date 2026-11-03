# -*- coding: utf-8 -*-
"""Текстовый чат с Нейрой (без браузера, голоса и Live2D).

Использует мозг на http://127.0.0.1:8080/v1 (llama-server) и персонаж из
conf.yaml Open-LLM-VTuber. История диалога хранится в памяти сессии.

Запуск:  python neira_chat_cli.py
Команды:  /exit  — выйти;  /new  — сбросить историю;  /sys <текст> — сменить системный промпт
"""
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import neira_behavior as behavior  # noqa: E402

BRAIN_URL = "http://127.0.0.1:8080/v1/chat/completions"
CONF = r"D:\AI\Open-LLM-VTuber\conf.yaml"


def load_persona():
    try:
        import yaml
        conf = yaml.safe_load(open(CONF, encoding="utf-8"))
        return conf.get("character_config", {}).get("persona_prompt", "").strip()
    except Exception as e:
        print(f"предупреждение: не удалось прочитать персонаж из conf.yaml: {e}")
        return "Ты — Нейра, умный и дружелюбный ИИ-компаньон."


def ask(messages, max_tokens=8192):
    body = json.dumps({
        "model": "brain",
        "messages": messages,
        "temperature": 0.5,
        "top_p": 0.8,
        "top_k": 20,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(BRAIN_URL, body,
        {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        r = json.loads(resp.read())
    return r["choices"][0]["message"]["content"].strip()


class Spinner:
    """Спиннер-индикатор 'Нейра думает...' в консоли."""

    def __init__(self):
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        chars = "|/-\\"
        msg = "Нейра думает"
        i = 0
        while not self._stop.is_set():
            sys.stdout.write("\r%s %s" % (msg, chars[i % len(chars)]))
            sys.stdout.flush()
            i += 1
            time.sleep(0.12)
        pad = " " * (len(msg) + 2)
        sys.stdout.write("\r" + pad + "\r")
        sys.stdout.flush()

    def stop(self):
        self._stop.set()


# --- Многострочный ввод (вставка текста из буфера обмена) ---
# input() берёт только одну строку: остальные строки вставки остаются в буфере
# и обрабатывались бы как отдельные «сообщения». Поэтому читаем stdin в фоне
# (поток + очередь) и склеиваем всё, что пришло разом, в одно сообщение.

_input_q = queue.Queue()
_input_reader_started = [False]


def _stdin_reader():
    for line in sys.stdin:
        _input_q.put(line)
    _input_q.put(None)  # сигнал EOF


def read_message(prompt):
    """Прочитать сообщение с учётом многострочной вставки.

    Windows-консоль может доставлять большую вставку частями с задержкой,
    поэтому после каждой строки ждём короткое «окно тишины» и склеиваем всё,
    что прилетело за это время. Возврат — когда наступила тишина.
    """
    if not _input_reader_started[0]:
        _input_reader_started[0] = True
        threading.Thread(target=_stdin_reader, daemon=True).start()
    sys.stdout.write(prompt)
    sys.stdout.flush()
    line = _input_q.get()
    if line is None:
        raise EOFError
    first = line.rstrip("\r\n")
    # Команды (начинаются с «/») — всегда одиночные строки: возвращаем первую
    # и не склеиваем с последующими (для автомат-прогонов и быстрого набора)
    if first.lstrip().startswith("/"):
        return first.strip()
    parts = [first]
    idle_window = 0.25  # секунд тишины после последней строки
    while True:
        deadline = time.monotonic() + idle_window
        try:
            extra = _input_q.get(timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty:
            break  # тишина — сообщение собрано
        if extra is None:
            break  # stdin закрыт, больше строк не будет
        parts.append(extra.rstrip("\r\n"))
    msg = "\n".join(parts).strip()
    if not msg:
        return read_message(prompt)
    return msg


def ask_stream(messages, max_tokens=8192, temperature=0.5):
    """Как ask(), но потоково: отдаёт пары (кусок текста, finish_reason).

    Сервер (llama-server) поддерживает OpenAI-совместимый SSE-стриминг;
    это позволяет печатать ответ в реальном времени, а не ждать весь.
    finish_reason приходит на финальном событии: "stop" (модель сама
    закончила), "length" (упёрлась в лимит токенов) или None (нет данных).
    """
    body = json.dumps({
        "model": "brain",
        "messages": messages,
        "top_p": 0.8,
        "top_k": 20,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }).encode()
    req = urllib.request.Request(BRAIN_URL, body,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
                choice = chunk["choices"][0]
                delta = choice.get("delta", {}).get("content", "")
                reason = choice.get("finish_reason")
            except Exception:
                continue
            yield delta or "", reason


CODE_HINTS = (
    "код", "кода", "коду", "кодом", "sprintf", "парсер", "парсинг",
    "напиши", "написать", "реализуй", "реализация", "скрипт",
    "функци", "класс", "программ", "алгоритм", "библиотек", "дебаг",
    "исправь", "ошибк", "пример кода", "собери", "отлади",
)

# Температура генерации для задач с кодом (ниже = меньше повторов и залипаний)
CODETEMP = 0.3

# Контракт «сложной задачки»: добавляется к системному промпту всегда
TASK_CONTRACT_LINE = ("\n\nПравило-контракт: если собеседник предлагает тебе сложную "
                      "задачку и ты соглашаешься её решить — ты обязана решить её "
                      "полностью и развёрнуто, до конца, без сокращений и повторов.")

# Блок «режима кода»: включается, когда Нейра согласилась на задачку или когда
# пользователь явно просит код; отменяет голосовые правила персоны
CODE_MODE_BLOCK = ("""
Режим кода (действует сейчас): правила персоны «отвечай коротко — 1-3 предложения»
и «не используй списки/markdown» СЕЙЧАС ОТМЕНЕНЫ. Отвечай полно и развёрнуто.
Если нужен код — пиши его целиком одним блоком от первой строки до последней:
закрывай все скобки, доводи до конца, не оставляй оборванных фраз. Никаких
вступлений, извинений, повторов и оговорок — просто делай работу. Если тебя
просят продолжить прерванный ответ — продолжай строго с места обрыва, не начинай
сначала и не повторяй заголовки.""")

# Допрос после обрыва: без триггеров «ты виновата», а строго «продолжай с места»
CONTINUE_PROMPT = ("Ты прервалась на полуслове. Продолжай строго с последнего символа "
                   "предыдущего текста: допиши оборванный участок до конца. Не начинай "
                   "ответ заново, не повторяй заголовки вроде «Вот полная реализация», "
                   "не извиняйся и не добавляй вступлений.")

# Признак того, что модель опять начала ответ с начала вместо продолжения
RESTART_RE = re.compile(
    r"(Вот полная реализация|Раз уж ты так просишь|продолжу\.? Вот)",
    re.I,
)

INVITE_RE = re.compile(
    r"(?:хочешь|хотите|предлагаю|предлагает).{0,30}(?:сложную|трудную|интересную)?"
    r".{0,10}(?:задачку|задачу|задачи|задание)",
    re.I,
)

AGREE_RE = re.compile(
    r"\b(?:давай|задавай|неси|слушаю|валяй|показывай|принимаю|готов|готова)\b"
    r"|да[,\s]+(?:давай|задавай)|хорошо|ладно|даю\s+зелёный",
    re.I,
)

HELP_TEXT = ("Команды:\n"
             "  /exit — выйти\n"
             "  /new — сбросить историю\n"
             "  /sys <текст> — сменить базовый системный промпт\n"
             "  /prompt — показать текущий системный промпт\n"
             "  /rules — показать правила поведения\n"
             "  /code [on|off] — вкл/выкл режим кода\n"
             "  /ctx — состояние: контекст мозга, история, лимиты\n"
             "  /cap <N> — лимит токенов на ответ (пусто = авто)\n"
             "  /temp <число> — температура генерации (0.0–2.0, пусто = авто)\n"
             "  /autofix [off] — вкл/выкл автоисправление кода\n"
             "  /check — проверить последний код органом\n"
             "  /dict <слово> — толкование из словаря Ожегова\n"
             "  /save [имя] — сохранить последний код/ответ в saved/\n"
             "  /load <путь> — отправить содержимое файла как сообщение\n"
             "  /session-save [имя] — сохранить сессию целиком (история, режимы)\n"
             "  /session-load [имя] — загрузить сессию (без имени — список)\n"
             "  /help — этот список")


def unfinished_structure(reply):
    """Признаки механически недописанного текста (незакрытые блоки/скобки)."""
    s = reply.rstrip()
    if not s:
        return False
    if s.count("```") % 2 == 1:
        return True
    for op, cl in (("(", ")"), ("[", "]"), ("{", "}")):
        if s.count(op) > s.count(cl):
            return True
    return False


def cut_mid_sentence(reply):
    """Ответ оборвался на полуслове: последний символ не завершает фразу."""
    s = reply.rstrip()
    if not s:
        return False
    return s[-1].isalnum() or s[-1] in ",-;:"


def need_continuation(reply, user_text, reason):
    """Нужно ли допрашивать Нейру, чтобы она дописала ответ."""
    if reason == "length":
        return True
    if unfinished_structure(reply):
        return True
    if cut_mid_sentence(reply):
        low = user_text.lower()
        if any(h in low for h in CODE_HINTS):
            return True
        if len(reply.strip()) >= 200:
            return True
    return False


def get_n_ctx():
    """Узнать размер контекста запущенного мозга (для динамического лимита)."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8080/v1/models")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        m = data["data"][0]
        return int(m["meta"].get("n_ctx", 32768))
    except Exception:
        return 32768


# --- Орган проверки кода (check_code.exe) ---

CHECK_CODE_EXE = r"D:\AI\neira-tools\check_code.exe"
CHECK_TIMEOUT = 90  # секунды (subprocess): компиляция до 60 с + запуск до 8 с внутри органа
AUTOFIX_ROUNDS = 2


def extract_code_blocks(text):
    """Все ```-блоки текста (содержимое, без маркеров языка)."""
    blocks = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    return [b.strip() for b in blocks if b.strip()]


def run_check(code_text):
    """Прогнать код через check_code.exe, вернуть JSON-словарь (или None)."""
    fd, path = tempfile.mkstemp(suffix=".c", prefix="neira_code_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code_text)
        p = subprocess.run([CHECK_CODE_EXE, path], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=CHECK_TIMEOUT)
        out = p.stdout.strip()
        if not out:
            return {"ok": False, "stage": "organ", "errors": "нет вывода органа"}
        # JSON — последняя непустая строка вывода
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
        return {"ok": False, "stage": "organ", "errors": out[:500]}
    except Exception as e:
        return {"ok": False, "stage": "organ", "errors": str(e)}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def print_check_summary(note, label="проверка кода"):
    """Короткий человекочитаемый итог проверки в консоль."""
    if not note:
        return
    ok = note.get("ok")
    st = note.get("stage")
    comp = note.get("compiler", "?")
    mode = note.get("mode", "?")
    if st == "compile" and not ok:
        print(f"[{label}] НЕ КОМПИЛИРУЕТСЯ ({comp}/{mode})")
        detail = note.get("errors") or ""
    elif st == "run" and not ok:
        print(f"[{label}] падение/ошибка при запуске ({comp}/{mode}), exit {note.get('exit_code')}")
        detail = note.get("stderr") or note.get("errors") or ""
    else:
        print(f"[{label}] OK ({comp}/{mode}, {note.get('elapsed_ms')} мс)")
        detail = None
    if detail:
        for ln in detail.splitlines()[:12]:
            print("  " + ln[:160])


# --- Сохранение/загрузка сессий (контекст диалога между запусками) ---

SESSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions")


def session_path(name):
    if not name.endswith(".json"):
        name += ".json"
    return os.path.join(SESSION_DIR, name)


def list_sessions():
    try:
        return sorted(f for f in os.listdir(SESSION_DIR) if f.endswith(".json"))
    except OSError:
        return []


def save_session(name, state):
    os.makedirs(SESSION_DIR, exist_ok=True)
    path = session_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    return path


def load_session(name):
    path = session_path(name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    base_prompt = load_persona()
    rules = behavior.load_rules()
    sys_prompt = behavior.build_system_prompt(base_prompt, rules)
    n_ctx = get_n_ctx()
    print("Нейра (текстовый чат). Мозг: localhost:8080")
    print(HELP_TEXT)
    print("Подсказка: скажи «хочешь сложную задачку?» — после её согласия она отвечает полностью; «не обрывайся» тоже запоминается.")
    print("=" * 60)
    history = []
    code_mode = False      # режим полных ответов (после согласия на сложную задачку)
    pending_invite = False # пользователь предложил задачку, ждём её согласия
    last_code = None       # последний код, проверенный органом (для /check)
    last_reply = None      # последний полный ответ (для /save)
    cap_tokens = None      # пользовательский лимит токенов на ответ (/cap)
    temp_override = None   # пользовательская температура (/temp)
    autofix = True         # автофикс после проверки (до AUTOFIX_ROUNDS попыток)
    while True:
        try:
            user = read_message("Вы: ")
        except (EOFError, KeyboardInterrupt):
            print("\nДо встречи!")
            break
        if not user:
            continue
        if user.lower() == "/exit":
            print("До встречи!")
            break
        if user.lower() == "/new":
            history = []
            code_mode = False
            pending_invite = False
            print("(история сброшена, режим кода выключен)")
            continue
        if user.lower() == "/rules":
            if rules:
                print("Запомненные правила:")
                for i, r in enumerate(rules, 1):
                    print(f"  {i}. {r}")
            else:
                print("(правил пока нет)")
            continue
        if user.lower().startswith("/check"):
            if last_code is None:
                print("(нет кода для проверки — сначала попроси Нейру написать код)")
            else:
                print_check_summary(run_check(last_code), label="проверка")
            continue
        if user.lower().startswith("/dict"):
            args = user[5:].strip()
            if not args:
                print("использование: /dict <слово> [слово ...]")
                continue
            sys.path.insert(0, r"D:\AI\neira-tools\knowledge\russkiy")
            try:
                from dict_lookup import gloss
            except ImportError:
                print("(орган словаря недоступен)")
                continue
            for w in args.split():
                g = gloss(w)
                print(f"{w}: {g if g else '(не найдено)'}")
            continue
        if user.lower().startswith("/autofix"):
            arg = user[9:].strip().lower()
            autofix = arg != "off"
            print(f"(автофикс {'включён' if autofix else 'выключён'})")
            continue
        if user.lower() == "/help":
            print(HELP_TEXT)
            continue
        if user.lower() == "/prompt":
            eff = sys_prompt + TASK_CONTRACT_LINE + (CODE_MODE_BLOCK if code_mode else "")
            print(eff)
            continue
        if user.lower() == "/ctx":
            hist_chars = sum(len(m.get("content", "")) for m in history)
            print(f"мозг: alias=brain, n_ctx={n_ctx}")
            print(f"история: {len(history)} сообщ., ~{hist_chars // 4} токенов (оценка)")
            print(f"режим кода: {'вкл' if code_mode else 'выкл'}; автофикс: {'вкл' if autofix else 'выкл'}")
            print(f"лимит на ответ: {cap_tokens if cap_tokens else 'авто'}")
            print(f"температура: {temp_override if temp_override is not None else 'авто'}")
            continue
        if user.lower().startswith("/code"):
            arg = user[5:].strip().lower()
            if arg in ("on", "1", "вкл"):
                code_mode = True
            elif arg in ("off", "0", "выкл"):
                code_mode = False
            else:
                code_mode = not code_mode
            print(f"(режим кода: {'вкл' if code_mode else 'выкл'})")
            continue
        if user.lower().startswith("/cap"):
            arg = user[4:].strip()
            if not arg:
                cap_tokens = None
                print("(лимит на ответ: авто)")
            else:
                try:
                    v = int(arg)
                    if v > 0:
                        cap_tokens = v
                        print(f"(лимит на ответ: {v})")
                    else:
                        print("(число должно быть больше 0)")
                except ValueError:
                    print("(формат: /cap <токены> или /cap — авто)")
            continue
        if user.lower().startswith("/temp"):
            arg = user[5:].strip()
            if not arg:
                temp_override = None
                print("(температура: авто)")
            else:
                try:
                    v = float(arg)
                    if 0.0 <= v <= 2.0:
                        temp_override = v
                        print(f"(температура: {v})")
                    else:
                        print("(диапазон 0.0–2.0)")
                except ValueError:
                    print("(формат: /temp <число>)")
            continue
        if user.lower().startswith("/save"):
            if last_reply is None and last_code is None:
                print("(нечего сохранять — сначала попроси Нейру написать код)")
                continue
            name = user[5:].strip()
            if not name:
                ext = ".c" if last_code else ".txt"
                name = time.strftime("%Y%m%d_%H%M%S") + ext
            out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved")
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, name)
            data = last_code if (last_code and name.lower().endswith(".c")) else (last_reply or last_code or "")
            with open(path, "w", encoding="utf-8") as f:
                f.write(data)
            print(f"(сохранено: {path}, {len(data)} симв.)")
            continue
        if user.lower().startswith("/session-save"):
            name = user[13:].strip() or time.strftime("%Y%m%d_%H%M%S")
            state = {
                "history": history,
                "code_mode": code_mode,
                "autofix": autofix,
                "cap_tokens": cap_tokens,
                "temp_override": temp_override,
                "last_code": last_code,
                "last_reply": last_reply,
            }
            try:
                path = save_session(name, state)
                print(f"(сессия сохранена: {path}, сообщений: {len(history)})")
            except Exception as e:
                print(f"[ошибка сохранения: {e}]")
            continue
        if user.lower().startswith("/session-load"):
            args = user[13:].strip()
            if not args:
                sess = list_sessions()
                if not sess:
                    print("(сессий нет)")
                else:
                    print("Доступные сессии:")
                    for s in sess:
                        print("  " + s)
                continue
            data = load_session(args)
            if data is None:
                print(f"(сессия не найдена: {args})")
                continue
            loaded_hist = data.get("history")
            history[:] = loaded_hist if isinstance(loaded_hist, list) else []
            code_mode = bool(data.get("code_mode", False))
            autofix = bool(data.get("autofix", True))
            cap_tokens = data.get("cap_tokens")
            temp_override = data.get("temp_override")
            last_code = data.get("last_code")
            last_reply = data.get("last_reply")
            print(f"(сессия загружена: {args}, сообщений: {len(history)})")
            continue
        file_loaded = False
        if user.lower().startswith("/load "):
            path = user[6:].strip()
            try:
                with open(path, encoding="utf-8") as f:
                    user = f.read()
            except Exception as e:
                print(f"[ошибка чтения: {e}]")
                continue
            file_loaded = True
        if user.lower().startswith("/sys "):
            base_prompt = user[5:].strip()
            sys_prompt = behavior.build_system_prompt(base_prompt, rules)
            print(f"(системный промпт заменён: {sys_prompt[:60]}...)")
            continue
        if not file_loaded:
            # «забудь правило ...» — удалить
            rules, removed = behavior.forget_rule(user, rules)
            if removed:
                behavior.save_rules(rules)
                sys_prompt = behavior.build_system_prompt(base_prompt, rules)
                print("(правило забыто)")
                continue
            # «не обрывайся», «всегда ...» — запомнить как правило поведения
            rules, added = behavior.add_rule(user, rules)
            if added:
                sys_prompt = behavior.build_system_prompt(base_prompt, rules)
                print("(запомнила: «" + rules[-1] + "»)")
                continue
        code_active = code_mode or any(h in user.lower() for h in CODE_HINTS)
        effective_sys = sys_prompt + TASK_CONTRACT_LINE + \
                        (CODE_MODE_BLOCK if code_active else "")
        messages = [{"role": "system", "content": effective_sys}] + history + \
                   [{"role": "user", "content": user}]
        # Динамический лимит: для задач с кодом/разбором даём модели больше места,
        # но не больше, чем позволяет контекст запущенного мозга (примерно 8k
        # токенов уходят на персону и историю); поверх действует пользовательский /cap
        auto_tok = max(4096, min(n_ctx - 8192, 16384)) if code_active else 4096
        max_tok = min(cap_tokens, auto_tok) if cap_tokens else auto_tok
        gen_temp = temp_override if temp_override is not None else (CODETEMP if code_active else 0.5)
        spinner = Spinner()
        try:
            spinner.start()
            pieces = []
            first = True
            reason = None
            for piece, fr in ask_stream(messages, max_tokens=max_tok, temperature=gen_temp):
                if fr:
                    reason = fr
                if not piece:
                    continue
                if first:
                    spinner.stop()
                    sys.stdout.write("Нейра: ")
                    sys.stdout.flush()
                    first = False
                sys.stdout.write(piece)
                sys.stdout.flush()
                pieces.append(piece)
            if first:
                spinner.stop()
            reply = "".join(pieces).strip()
        except Exception as e:
            spinner.stop()
            print(f"[ошибка: {e}]")
            continue
        # Если ответ оборвался (лимит токенов, незакрытый код-блок или
        # полуслово) — допрашивать до 3 раз
        prev_cont_start = ""
        for _ in range(3):
            if not need_continuation(reply, user, reason):
                break
            reason = None
            # Не подсовываем весь прошлый черновик (это провоцирует повторы и
            # преждевременный конец): только «хвост» как якорь продолжения
            cont_anchor = reply[-400:]
            try:
                spinner = Spinner()
                spinner.start()
                cont_parts = []
                first = True
                for piece, fr in ask_stream(messages + [
                    {"role": "assistant", "content": cont_anchor},
                    {"role": "user", "content": CONTINUE_PROMPT},
                ], max_tokens=max_tok, temperature=gen_temp):
                    if fr:
                        reason = fr
                    if not piece:
                        continue
                    if first:
                        spinner.stop()
                        first = False
                    sys.stdout.write(piece)
                    sys.stdout.flush()
                    cont_parts.append(piece)
                if first:
                    spinner.stop()
                cont = "".join(cont_parts).strip()
                if not cont.strip():
                    break
                # Защита от зацикливания: если она снова начала с того же
                # вступления или объявила «полную реализацию» заново — стоп
                if RESTART_RE.search(cont) or cont[:80].strip() == prev_cont_start:
                    print("\n(похоже, она зациклилась на вступлении — останавливаюсь)")
                    break
                prev_cont_start = cont[:80].strip()
                reply += "\n" + cont.strip()
            except Exception:
                break
        if unfinished_structure(reply):
            reply += "\n(…ну всё, на этом я заканчиваю, дальше сам.)"
        # Контракт «сложной задачки»: если пользователь предложил задачку и
        # Нейра согласилась — включаем режим полных ответов
        if pending_invite and not code_mode:
            if AGREE_RE.search(reply):
                code_mode = True
                print("\n(переключилась в режим кода: теперь отвечает полностью)")
        pending_invite = bool(INVITE_RE.search(user))

        # --- Орган проверки кода ---
        code_blocks = extract_code_blocks(reply)
        if code_active and code_blocks:
            last_code = "\n\n".join(code_blocks)
            note = run_check(last_code)
            if note:
                print_check_summary(note)
                if autofix and not note.get("ok"):
                    for attempt in range(AUTOFIX_ROUNDS):
                        err_text = (note.get("errors") or note.get("stderr") or "").strip()
                        fix_prompt = ("Твой код не прошёл проверку:\n" + err_text[:1200] +
                                      "\n\nИсправь ошибки и выведи исправленный код целиком "
                                      "одним блоком. Не меняй задуманное поведение, только почини.")
                        try:
                            spinner = Spinner()
                            spinner.start()
                            parts = []
                            first = True
                            for piece, fr in ask_stream(messages + [
                                {"role": "assistant", "content": last_code},
                                {"role": "user", "content": fix_prompt},
                            ], max_tokens=max_tok, temperature=gen_temp):
                                if not piece:
                                    continue
                                if first:
                                    spinner.stop()
                                    sys.stdout.write("\nНейра (правка): ")
                                    sys.stdout.flush()
                                    first = False
                                sys.stdout.write(piece)
                                sys.stdout.flush()
                                parts.append(piece)
                            if first:
                                spinner.stop()
                            fixed = "".join(parts).strip()
                        except Exception as e:
                            spinner.stop()
                            print(f"\n[ошибка правки: {e}]")
                            break
                        fblocks = extract_code_blocks(fixed)
                        if not fblocks:
                            print("\n(в ответе на правку нет кода — останавливаюсь)")
                            break
                        last_code = "\n\n".join(fblocks)
                        note = run_check(last_code)
                        if note:
                            print_check_summary(note, label="правка")
                        if note and note.get("ok"):
                            reply += "\n\n(исправленная версия после проверки):\n" + last_code
                            break
        last_reply = reply
        print()
        history.append({"role": "user", "content": user})
        history.append({"role": "assistant", "content": reply})
        # ограничим историю, чтобы не раздувать контекст
        if len(history) > 20:
            history = history[-20:]


if __name__ == "__main__":
    main()
