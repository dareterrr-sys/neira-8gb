"""Neira's C code checking organ for the voice app (04.11.2026, the author: «Подключить»; register item 8).
The same logic as the text chat (neira_chat_cli.py: extract_code_blocks, run_check, the autofix prompt), moved here so
the app can load it like its other organs; the CLI itself is not changed. check_code.exe compiles a .c file, runs it
under ASan/UBSan with a timeout and prints JSON {ok, stage, mode, compiler, exit_code, errors, stdout, stderr,
elapsed_ms}."""
import json
import os
import re
import subprocess
import tempfile

CHECK_CODE_EXE = os.environ.get("NEIRA_CHECK_CODE_EXE", r"D:\AI\neira-tools\check_code.exe")
CHECK_TIMEOUT = 90  # seconds (subprocess): compile up to 60 s + run up to 8 s inside the organ (as in the CLI)
AUTOFIX_ROUNDS = 2  # as in the CLI

# a fenced block: its language tag and its content
_BLOCK = re.compile(r"```([^\n]*)\n(.*?)```", re.S)
# check_code compiles C only: a block tagged c/h, or untagged but plainly C (the CLI checked every block in code mode)
_C_TAGS = {"c", "h"}
_C_LOOKS = re.compile(r"#include\s*<[\w./]+\.h>|\bint\s+main\s*\(", re.S)

FIX_PROMPT = ("Твой код не прошёл проверку:\n{errors}\n\nИсправь ошибки и выведи исправленный код целиком "
              "одним блоком. Не меняй задуманное поведение, только почини.")   # the CLI's words


def extract_code_blocks(text):
    """All ```-blocks of the text (content, without the language marker) - as in the CLI."""
    return [b.strip() for _, b in _BLOCK.findall(text or "") if b.strip()]


def extract_c_blocks(text):
    """The ```-blocks that are C code."""
    out = []
    for tag, body in _BLOCK.findall(text or ""):
        tag, body = tag.strip().lower(), body.strip()
        if body and (tag in _C_TAGS or (not tag and _C_LOOKS.search(body))):
            out.append(body)
    return out


def run_check(code_text):
    """Run the code through check_code.exe, return its JSON dict - the CLI's run_check."""
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
        # the JSON is the last non-empty line of the output
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


def summary(note):
    """One line for the log - the CLI's print_check_summary, without printing."""
    if not note:
        return "нет результата"
    st, comp, mode = note.get("stage"), note.get("compiler", "?"), note.get("mode", "?")
    if st == "compile" and not note.get("ok"):
        return f"НЕ КОМПИЛИРУЕТСЯ ({comp}/{mode}): {(note.get('errors') or '')[:300]}"
    if st == "run" and not note.get("ok"):
        return (f"падение/ошибка при запуске ({comp}/{mode}), exit {note.get('exit_code')}: "
                f"{(note.get('stderr') or note.get('errors') or '')[:300]}")
    if not note.get("ok"):
        return f"ошибка органа ({st}): {(note.get('errors') or '')[:300]}"
    return f"OK ({comp}/{mode}, {note.get('elapsed_ms')} мс)"


def fix_prompt(note):
    """The CLI's autofix request for a failed check."""
    err = (note.get("errors") or note.get("stderr") or "").strip()
    return FIX_PROMPT.format(errors=err[:1200])


def available():
    return os.path.isfile(CHECK_CODE_EXE)
