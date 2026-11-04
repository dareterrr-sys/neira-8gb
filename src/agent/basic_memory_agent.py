from typing import (
    AsyncIterator,
    List,
    Dict,
    Any,
    Callable,
    Literal,
    Union,
    Optional,
)
import asyncio
import datetime
import time
import os
import re

from loguru import logger
from .agent_interface import AgentInterface
from ..output_types import SentenceOutput, DisplayText
from ..stateless_llm.stateless_llm_interface import StatelessLLMInterface
from ..stateless_llm.claude_llm import AsyncLLM as ClaudeAsyncLLM
from ..stateless_llm.openai_compatible_llm import AsyncLLM as OpenAICompatibleAsyncLLM
from ...chat_history_manager import get_history
from ..transformers import (
    sentence_divider,
    actions_extractor,
    tts_filter,
    display_processor,
)
from ...config_manager import TTSPreprocessorConfig
from ..input_types import BatchInput, TextSource
from prompts import prompt_loader
from ...mcpp.tool_manager import ToolManager
from ...mcpp.json_detector import StreamJSONDetector
from ...mcpp.types import ToolCallObject
from ...mcpp.tool_executor import ToolExecutor

# Neira's dispatcher (BasicMemoryAgent._dispatch): which user turns need the clock or the calculator.
_NUM_WORD = re.compile(
    r"\b(?:ноль|нул\w*|один|одн\w*|два|две|двух|двум\w*|три|тр[её]х|четыр\w*|пят[ьи]\w*|шест[ьи]\w*|сем[ьи]\w*"
    r"|восем\w*|девят\w*|десят\w*|\w+надцат\w*|двадцат\w*|тридцат\w*|сорок\w*|\w+десят\w*|девяност\w*"
    r"|сто|ста|сотн\w*|двест\w*|трист\w*|\w+сот|тысяч\w*|миллион\w*|миллиард\w*|половин\w*|процент\w*)\b",
    re.I)
_MATH_WORD = re.compile(r"(посчита|вычисл|умнож|раздел|подели|делить|сложи|вычти|плюс|минус|процент|корен|квадрат"
                        r"|степен|сколько будет|сумм[аыу]|средне|дроб|уравнен)", re.I)


# Only questions about the present moment: council v1 showed the clock poisoning puzzles ("Сегодня среда. Какой день
# недели будет через десять дней?" got "it is Tuesday"; "на какой день улитка доберётся" too).
_TIME_ASK = re.compile(r"(котор\w* (сейчас )?час|сколько (сейчас )?времени|сколько время|какое (сегодня|сейчас) число"
                       r"|какое число сегодня|какой (сегодня|сейчас) (день|год|месяц)|какая (сегодня|сейчас) дата"
                       r"|сегодня какое число|какой сегодня день недели|какой день недели сегодня)", re.I)
_TIME_PUZZLE = re.compile(r"(через|если|было|будет|вчера|завтра|сегодня (понедельник|вторник|сред|четверг|пятниц|суббот"
                          r"|воскресень))", re.I)


def asks_time(text: str) -> bool:
    return bool(_TIME_ASK.search(text)) and not _TIME_PUZZLE.search(text)


MATH_SPECIALIST = (
    "Ты помощник-вычислитель. Переведи задачу пользователя в ОДНО арифметическое выражение, значение которого и есть "
    "ответ на вопрос. Пиши только выражение цифрами и знаками + - * / ** и скобками, без слов и без знака =. "
    "Время суток считай в часах (например, 10 + 2). Если в сообщении нет задачи на счёт, ответь словом НЕТ.")
# a second, independent way to the expression: council v1 had one wrong expression ("24 / 3 - 24 + 7") poison every
# specialist downstream, so a note is trusted only when two different routes give the same number
MATH_SPECIALIST_2 = (
    "Ты внимательный вычислитель. Сначала одной строкой перескажи, что дано и что спрашивают, затем последней строкой "
    "выпиши ОДНО арифметическое выражение (цифры, + - * / ** и скобки, без знака =), значение которого — ответ. "
    "Если в сообщении нет задачи на счёт, ответь словом НЕТ.")


MATH_SPECIALIST_3 = (
    "Ты проверяющий вычислитель. Сначала одной строкой назови, что именно спрашивают и в каких единицах, затем "
    "последней строкой выпиши ОДНО арифметическое выражение (цифры, + - * / ** и скобки, без знака =), значение "
    "которого — ответ. Если в сообщении нет задачи на счёт, ответь словом НЕТ.")
MATH_ROUTES = ((MATH_SPECIALIST, 40), (MATH_SPECIALIST_2, 120), (MATH_SPECIALIST_3, 120))


def math_note(*answers: str) -> str:
    """The calculator's note from independently written expressions (council v2.1): the routes vote by result.
    Two or more agree -> a checked note the brain must not recount (v2 recounted a right 1000 into "788"); all
    disagree -> no note at all (v2 let a wrong second route split the specialists); a single route -> a plain note."""
    results = []
    for a in answers:
        e = (a or "").strip().strip("`").strip()
        e = e.splitlines()[-1].strip().strip("`").strip() if e else ""
        # v3.10_ru, 25.10: запятая в выражении — это перечисление ответов («2,4»), а не десятичная дробь
        # (восприятие уже пишет дроби точкой: «полтора» → 1.5); справка по списку отравляет совет
        if e and "НЕТ" not in e.upper() and "," not in e:
            r = calculate_text(e)
            if not r.startswith("Ошибка"):
                results.append((e, r, r.split(" ")[0]))
    if not results:
        return ""
    votes = {}
    for e, r, v in results:
        votes.setdefault(v, []).append((e, r))
    value, routes = max(votes.items(), key=lambda kv: len(kv[1]))
    if len(routes) >= 2:
        e, r = routes[0]
        # agreeing routes check the arithmetic, not the reading of the problem: in v2.1 two routes agreed on the same
        # misread "(30 - 5) / 2" and the note led the controllers away from the right answer
        return (f"Справка калькулятора ({len(routes)} способа из {len(results)} сошлись): {e} = {r}. Арифметика "
                f"проверена, не пересчитывай её в уме; но проверь, правильно ли выражение понимает условие.")
    if len(results) == 1:
        e, r = results[0][:2]
        return f"Справка калькулятора (выражение составлено помощником, проверь его по условию): {e} = {r}."
    return ""
_WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
           "ноября", "декабря"]


def _now_ru() -> str:
    """The PC's local time (it runs on Moscow time) in Russian words the brain can repeat."""
    n = datetime.datetime.now()
    return f"сейчас {n:%H:%M}, {_WEEKDAYS[n.weekday()]}, {n.day} {_MONTHS[n.month - 1]} {n.year} года"


def _load_calculator():
    """calculate_text() of Neira's calculator server (D:\\AI\\neira-tools\\calc_server.py), without MCP."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "neira_calc", os.environ.get("NEIRA_CALC", r"D:\AI\neira-tools\calc_server.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.calculate_text


def _load_tool(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Neira's long-term memory (D:\AI\neira-tools\neira_memory.py): recalled by cues in each user turn, written after it.
# NEIRA_MEMORY=0 turns it off.
NEIRA_MEMORY = None
_neira_memory = None
if os.environ.get("NEIRA_MEMORY", "1") != "0":
    try:
        _neira_memory = _load_tool("neira_memory", os.environ.get("NEIRA_MEMORY_PY", r"D:\AI\neira-tools\neira_memory.py"))
        NEIRA_MEMORY = _neira_memory.Memory()
        logger.info(f"Neira memory: {len(NEIRA_MEMORY.facts)} facts loaded")
    except Exception as _e:
        logger.warning(f"Neira memory not loaded: {_e}")

try:
    calculate_text = _load_calculator()
except Exception as _e:  # no calculator: the dispatcher only reads the clock
    logger.warning(f"Neira calculator not loaded: {_e}")
    calculate_text = lambda expr: "Ошибка: калькулятор не загружен"  # noqa: E731

# Neira's perception (D:\AI\neira-tools\perception.py): number words -> digits before any model reads the message
# ("две тысячи сотый" was read as 2000 by the whole council). NEIRA_PERCEPTION=0 turns it off.
perceive = lambda text: text  # noqa: E731
if os.environ.get("NEIRA_PERCEPTION", "1") != "0":
    try:
        perceive = _load_tool("perception", os.environ.get("NEIRA_PERCEPTION_PY", r"D:\AI\neira-tools\perception.py")).numbers_to_digits
    except Exception as _e:
        logger.warning(f"Neira perception not loaded: {_e}")

# Neira's calendar department (D:\AI\neira-tools\calendar_dept.py): days, dates, clock time, time zones, centuries
# and leap years are computed by code from a call two routes agree on. NEIRA_CALENDAR=0 turns it off.
CALENDAR = None
if os.environ.get("NEIRA_CALENDAR", "1") != "0":
    try:
        CALENDAR = _load_tool("calendar_dept", os.environ.get("NEIRA_CALENDAR_PY", r"D:\AI\neira-tools\calendar_dept.py"))
    except Exception as _e:
        logger.warning(f"Neira calendar not loaded: {_e}")

# Neira's letters department (D:\AI\neira-tools\letters_dept.py + bukvy.exe): letters, vowels, syllables, the n-th
# letter, reversals - the model sees tokens, not letters. NEIRA_LETTERS=0 turns it off.
LETTERS = None
if os.environ.get("NEIRA_LETTERS", "1") != "0":
    try:
        LETTERS = _load_tool("letters_dept", os.environ.get("NEIRA_LETTERS_PY", r"D:\AI\neira-tools\letters_dept.py"))
    except Exception as _e:
        logger.warning(f"Neira letters department not loaded: {_e}")

# Neira's words and units departments (25.10; slova_dept.py + slova.exe, edinicy_dept.py + edinicy.exe): counting
# words, the n-th word, substrings, alphabetical order, anagrams; converting units to SI and between units.
# On their own 60 questions the brain went 27 -> 47 right with the notes, no harm found elsewhere.
# NEIRA_WORDS=0 / NEIRA_UNITS=0 turn them off.
ORGANS = []   # (name, module, asks, routes, note)
for _env, _name, _py, _asks, _routes, _note in (
        ("NEIRA_WORDS", "slova_dept", r"D:\AI\neira-tools\slova_dept.py", "asks_words", "SLOVA_ROUTES", "words_note"),
        ("NEIRA_UNITS", "edinicy_dept", r"D:\AI\neira-tools\edinicy_dept.py", "asks_units", "EDINICY_ROUTES",
         "units_note")):
    if os.environ.get(_env, "1") != "0":
        try:
            _m = _load_tool(_name, _py)
            ORGANS.append((_name, _m, getattr(_m, _asks), getattr(_m, _routes), getattr(_m, _note)))
        except Exception as _e:
            logger.warning(f"Neira {_name} not loaded: {_e}")

# Neira's Russian department (27.10; russkiy_dept.py + russkiy.exe): EGE tasks a dictionary decides - stress (4),
# the missing letter (9-12), Н/НН (15) - over OpenCorpora, Hunspell, RUAccent and the FIPI list; it answers only when
# its routes agree (bank of 1122 real tasks: 499/499 right; council on the EGE Russian set 10 -> 16 of 34, 0 false
# triggers on 1796 other questions). NEIRA_RUSSKIY_DEPT=0 turns it off.
RUSSKIY = None
if os.environ.get("NEIRA_RUSSKIY_DEPT", "1") != "0":
    try:
        RUSSKIY = _load_tool("russkiy_dept", r"D:\AI\neira-tools\russkiy_dept.py")
    except Exception as _e:
        logger.warning(f"Neira russkiy_dept not loaded: {_e}")

# Neira's EGE organ (28.10; council/ege_one.py): an EGE Russian task the dictionaries did not decide is solved by ONE
# brain call with short thinking (<= 750 tokens; past tasks 47/72 right vs the council's 37/72), apart from the chat,
# so she does not reason aloud in circles. NEIRA_EGE_ONE=0 turns it off.
EGE_ONE = None
OWN_NOTES = ("Это твоё собственное знание: отвечай естественно, своими словами, как будто просто знаешь это.")
# the brain voices an organ's answer, it does not solve the task again aloud (it went in circles for 9 minutes)
EGE_SAY = (" Не решай задание заново и не рассуждай вслух: назови этот ответ и объясни его коротко, в двух-трёх "
           "предложениях, только по тому, что здесь написано.")
if os.environ.get("NEIRA_EGE_ONE", "1") != "0":
    try:
        EGE_ONE = _load_tool("ege_one", r"D:\AI\neira-tools\council\ege_one.py")
        EGE_ONE.is_ege_ru("прогрев")   # loads the Russian organ's dictionaries now, not on the first task (~25 s)
    except Exception as _e:
        logger.warning(f"Neira ege_one not loaded: {_e}")

# Neira's literacy filter (28.10; russkiy/gramota.py): every sentence she says gets spacing fixed and the commas the
# fine-tuned RUPunct net is sure of (held-out prose: <1% of correct sentences changed, ~63% of broken ones fixed),
# before subtitles and voice. GRAMOTA=0 turns it off.
GRAMOTA = None
if os.environ.get("GRAMOTA", "1") != "0":
    try:
        GRAMOTA = _load_tool("gramota", r"D:\AI\neira-tools\russkiy\gramota.py")
    except Exception as _e:
        logger.warning(f"Neira gramota not loaded: {_e}")

# Neira's council v4.0 in live chat (29.10, plan step 15; council/council_live.py): a task or a fact question
# (council_router: 94-98% of the test sets, 0 of the author's 36 chat lines) is solved by three quick specialists
# and, when they disagree, a thinker; the conclusion comes back as a note she says in her own words.
# NEIRA_COUNCIL=0 turns it off.
COUNCIL = None
if os.environ.get("NEIRA_COUNCIL", "1") != "0":
    try:
        COUNCIL = _load_tool("council_live", r"D:\AI\neira-tools\council\council_live.py")
    except Exception as _e:
        logger.warning(f"Neira council not loaded: {_e}")

# The voice gives the GPU to the brain on a hard turn (28.10; neira-tools/voice_swap.py): Neira says she needs to
# think, the voice server leaves, the specialists and the brain work alone, the voice comes back for the answer.
# NEIRA_VOICE_SWAP=0 turns it off.
VOICE_SWAP = None
if os.environ.get("NEIRA_VOICE_SWAP", "1") != "0":
    try:
        VOICE_SWAP = _load_tool("voice_swap", r"D:\AI\neira-tools\voice_swap.py")
    except Exception as _e:
        logger.warning(f"Neira voice_swap not loaded: {_e}")

# Neira's C code checking organ (04.11, the author: «Подключить»; neira-tools/check_code_organ.py = the text chat's
# check): a C block in her answer is compiled and run under ASan/UBSan by check_code.exe. NEIRA_CHECK_CODE=0 turns it off.
CHECK_CODE = None
if os.environ.get("NEIRA_CHECK_CODE", "1") != "0":
    try:
        CHECK_CODE = _load_tool("check_code_organ", r"D:\AI\neira-tools\check_code_organ.py")
        if not CHECK_CODE.available():
            raise FileNotFoundError(CHECK_CODE.CHECK_CODE_EXE)
    except Exception as _e:
        CHECK_CODE = None
        logger.warning(f"Neira check_code not loaded: {_e}")

# 04.11, the build self-check (field_tests/build_check.py reads this line): which organs are loaded and the council mode
_ORGAN_STATE = {
    "memory": NEIRA_MEMORY is not None,
    "calculator": not calculate_text("2+2").startswith("Ошибка"),
    "perception": getattr(perceive, "__name__", "") != "<lambda>",
    "calendar": CALENDAR is not None,
    "letters": LETTERS is not None,
    "words": any(n == "slova_dept" for n, *_ in ORGANS),
    "units": any(n == "edinicy_dept" for n, *_ in ORGANS),
    "russkiy": RUSSKIY is not None,
    "ege_one": EGE_ONE is not None,
    "gramota": GRAMOTA is not None,
    "council": COUNCIL is not None,
    "voice_swap": VOICE_SWAP is not None,
    "check_code": CHECK_CODE is not None,
}
logger.info("Neira organs: loaded=" + ",".join(k for k, v in _ORGAN_STATE.items() if v)
            + "; missing=" + (",".join(k for k, v in _ORGAN_STATE.items() if not v) or "none")
            + f"; COUNCIL_EXPR={os.environ.get('COUNCIL_EXPR', '0')}"
            + f" (council uses {int(bool(COUNCIL and COUNCIL.council.EXPR))})"
            + f"; NEIRA_CHECK_CODE={os.environ.get('NEIRA_CHECK_CODE', '1')}")


def gramota_filter():
    """Between sentence_divider and actions_extractor: fix each spoken sentence (not <think>)."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            async for item in func(*args, **kwargs):
                if GRAMOTA and hasattr(item, "text") and not any(t.name == "think" for t in item.tags):
                    try:
                        fixed = await asyncio.to_thread(GRAMOTA.fix, item.text)
                        if fixed != item.text:
                            logger.info(f"Gramota: {item.text!r} -> {fixed!r}")
                            item.text = fixed
                    except Exception as e:
                        logger.warning(f"Gramota failed: {e}")
                yield item
        return wrapper
    return decorator


# v3.10_ru, 25.10: «Укажите варианты ответов / номера ответов …» (ЕГЭ) — это перечисление, а не счёт:
# номера вариантов («2,4») превращались в десятичную дробь 2.4 и отравляли совет ложной справкой
_NO_CALC = re.compile(r"варианты[ ]+ответов|номера[ ]+ответов|номер[ ]+ответа|импишите[ ]+номер(а|ов)?|"
                      r"укажите[ ]+цифру|предложения,[ ]+в которых|укажите[ ]+предложения", re.I)


# Bare arithmetic (29.10, the author: «why the calculator then?»): «сколько будет 3847 × 2919?», «17,5% от 128 640» -
# code computes it directly, no brain calls (the calculator's three expression-writing calls took 10-14 s); a word
# problem goes to the council, which on work3/hard was as right without the calculator and ~30% faster.
_ASK = re.compile(r"^(?:а\s+)?(?:сколько будет|сколько|посчитай|вычисли|подсчитай|чему равно|чему равен|реши)\s*:?\s*",
                  re.I)
_PCT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%\s*от\s*(\d+(?:[.,]\d+)?)", re.I)
_EXPR = re.compile(r"^[\d\s.,+\-*/×·÷:^()−]+$")


def direct_math(text: str):
    """-> "expression = result" for a bare arithmetic question, else None."""
    t = _ASK.sub("", (text or "").strip()).rstrip(" ?!.=")
    t = re.sub(r"(?<=\d)\s+(?=\d{3}\b)", "", t)          # 128 640 -> 128640
    t = _PCT.sub(lambda m: f"({m.group(1)}/100*{m.group(2)})", t)
    if not t or not re.search(r"\d\s*[-+*/×·÷:^−]\s*\(?\d", t) or not _EXPR.match(t.replace(" ", "")):
        return None
    expr = t.replace(":", "/")
    result = calculate_text(expr)
    return None if result.startswith("Ошибка") else f"{expr} = {result}"


def needs_calculator(text: str) -> bool:
    if _NO_CALC.search(text):
        return False
    nums = len(re.findall(r"\d+(?:[.,]\d+)?", text)) + len(_NUM_WORD.findall(text))
    return bool(_MATH_WORD.search(text)) or nums >= 2


class BasicMemoryAgent(AgentInterface):
    """Agent with basic chat memory and tool calling support."""

    _system: str = "You are a helpful assistant."

    def __init__(
        self,
        llm: StatelessLLMInterface,
        system: str,
        live2d_model,
        tts_preprocessor_config: TTSPreprocessorConfig = None,
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
        use_mcpp: bool = False,
        interrupt_method: Literal["system", "user"] = "user",
        tool_prompts: Dict[str, str] = None,
        tool_manager: Optional[ToolManager] = None,
        tool_executor: Optional[ToolExecutor] = None,
        mcp_prompt_string: str = "",
    ):
        """Initialize agent with LLM and configuration."""
        super().__init__()
        self._memory = []
        self._live2d_model = live2d_model
        self._tts_preprocessor_config = tts_preprocessor_config
        self._faster_first_response = faster_first_response
        self._segment_method = segment_method
        self._use_mcpp = use_mcpp
        self.interrupt_method = interrupt_method
        self._tool_prompts = tool_prompts or {}
        self._interrupt_handled = False
        self.prompt_mode_flag = False
        self._last_code_check = None   # the check_code organ's last result: {"code", "note"}

        self._tool_manager = tool_manager
        self._tool_executor = tool_executor
        self._mcp_prompt_string = mcp_prompt_string
        self._json_detector = StreamJSONDetector()

        self._formatted_tools_openai = []
        self._formatted_tools_claude = []
        if self._tool_manager:
            self._formatted_tools_openai = self._tool_manager.get_formatted_tools(
                "OpenAI"
            )
            self._formatted_tools_claude = self._tool_manager.get_formatted_tools(
                "Claude"
            )
            logger.debug(
                f"Agent received pre-formatted tools - OpenAI: {len(self._formatted_tools_openai)}, Claude: {len(self._formatted_tools_claude)}"
            )
        else:
            logger.debug(
                "ToolManager not provided, agent will not have pre-formatted tools."
            )

        self._set_llm(llm)
        self.set_system(system if system else self._system)

        if self._use_mcpp and not all(
            [
                self._tool_manager,
                self._tool_executor,
                self._json_detector,
            ]
        ):
            logger.warning(
                "use_mcpp is True, but some MCP components are missing in the agent. Tool calling might not work as expected."
            )
        elif not self._use_mcpp and any(
            [
                self._tool_manager,
                self._tool_executor,
                self._json_detector,
            ]
        ):
            logger.warning(
                "use_mcpp is False, but some MCP components were passed to the agent."
            )

        logger.info("BasicMemoryAgent initialized.")

    def _set_llm(self, llm: StatelessLLMInterface):
        """Set the LLM for chat completion."""
        self._llm = llm
        self.chat = self._chat_function_factory()

    def set_system(self, system: str):
        """Set the system prompt."""
        logger.debug(f"Memory Agent: Setting system prompt: '''{system}'''")

        if self.interrupt_method == "user":
            system = f"{system}\n\nIf you received `[interrupted by user]` signal, you were interrupted."

        self._system = system

    def _add_message(
        self,
        message: Union[str, List[Dict[str, Any]]],
        role: str,
        display_text: DisplayText | None = None,
        skip_memory: bool = False,
    ):
        """Add message to memory."""
        if skip_memory:
            return

        text_content = ""
        if isinstance(message, list):
            for item in message:
                if item.get("type") == "text":
                    text_content += item["text"] + " "
            text_content = text_content.strip()
        elif isinstance(message, str):
            text_content = message
        else:
            logger.warning(
                f"_add_message received unexpected message type: {type(message)}"
            )
            text_content = str(message)

        if not text_content and role == "assistant":
            return

        message_data = {
            "role": role,
            "content": text_content,
        }

        if display_text:
            if display_text.name:
                message_data["name"] = display_text.name
            if display_text.avatar:
                message_data["avatar"] = display_text.avatar

        if (
            self._memory
            and self._memory[-1]["role"] == role
            and self._memory[-1]["content"] == text_content
        ):
            return

        self._memory.append(message_data)

    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        """Load memory from chat history."""
        messages = get_history(conf_uid, history_uid)

        self._memory = []
        for msg in messages:
            role = "user" if msg["role"] == "human" else "assistant"
            content = msg["content"]
            if isinstance(content, str) and content:
                self._memory.append(
                    {
                        "role": role,
                        "content": content,
                    }
                )
            else:
                logger.warning(f"Skipping invalid message from history: {msg}")
        logger.info(f"Loaded {len(self._memory)} messages from history.")

    def handle_interrupt(self, heard_response: str) -> None:
        """Handle user interruption."""
        if self._interrupt_handled:
            return

        self._interrupt_handled = True

        if self._memory and self._memory[-1]["role"] == "assistant":
            if not self._memory[-1]["content"].endswith("..."):
                self._memory[-1]["content"] = heard_response + "..."
            else:
                self._memory[-1]["content"] = heard_response + "..."
        else:
            if heard_response:
                self._memory.append(
                    {
                        "role": "assistant",
                        "content": heard_response + "...",
                    }
                )

        interrupt_role = "system" if self.interrupt_method == "system" else "user"
        self._memory.append(
            {
                "role": interrupt_role,
                "content": "[Interrupted by user]",
            }
        )
        logger.info(f"Handled interrupt with role '{interrupt_role}'.")

    def _to_text_prompt(self, input_data: BatchInput) -> str:
        """Format input data to text prompt."""
        message_parts = []

        for text_data in input_data.texts:
            if text_data.source == TextSource.INPUT:
                message_parts.append(text_data.content)
            elif text_data.source == TextSource.CLIPBOARD:
                message_parts.append(
                    f"[User shared content from clipboard: {text_data.content}]"
                )

        if input_data.images:
            message_parts.append("\n[User has also provided images]")

        return "\n".join(message_parts).strip()

    async def _dispatch(self, messages: List[Dict[str, Any]]) -> None:
        """Neira's dispatcher: before the brain answers, specialists add facts to this turn's request (not to the
        chat history). Asking the brain to call tools proved unreliable mid-conversation: it starts with an emotion
        tag and then counts in its head. So the clock is read here, and a counting question goes to a short persona-
        free request that only writes the expression (8 of 8 right in a test), which the calculator evaluates."""
        self._turn_text = ""
        last = messages[-1] if messages else None
        if not last or last.get("role") != "user" or not isinstance(last.get("content"), list):
            return
        part = next((p for p in last["content"] if p.get("type") == "text"), None)
        if not part:
            return
        text, notes = part["text"], []
        self._turn_text = text   # memory keeps the words as said
        try:
            seen = perceive(text)
            if seen != text:
                logger.info(f"Dispatcher: perceived {seen!r}")
                part["text"] = text = seen
        except Exception as e:
            logger.warning(f"Dispatcher: perception failed: {e}")
        t0 = time.perf_counter()
        timing = {}
        if NEIRA_MEMORY:
            try:
                t = time.perf_counter()
                recalled = await asyncio.to_thread(NEIRA_MEMORY.recall, text)
                timing["memory"] = time.perf_counter() - t
                if recalled:
                    notes.append("Ты помнишь о собеседнике: " + "; ".join(recalled) + ".")
                    logger.info(f"Dispatcher: memory recalled {recalled}")
            except Exception as e:
                logger.warning(f"Dispatcher: memory recall failed: {e}")
        # an EGE task goes to the Russian organs only (the letters organ fired on one and thought 105 s)
        ege = bool(EGE_ONE and EGE_ONE.is_ege_ru(text))
        if asks_time(text):
            notes.append("Справка часов: " + _now_ru() + ".")
            logger.info("Dispatcher: a time question -> clock")
        # a council turn solves the count itself: the calculator first cost 10-14 s and once misled it (24/3+7=15);
        # NEIRA_COUNCIL_CALC=1 keeps it (the measurement on the sets decides)
        bare = direct_math(text)
        if bare:
            notes.append(f"Справка калькулятора (посчитано кодом): {bare}.")
            logger.info(f"Dispatcher: bare arithmetic -> {bare}")
        council_turn = bool(COUNCIL and not bare and not (EGE_ONE and EGE_ONE.is_ege_ru(text))
                            and COUNCIL.needs_council(text))
        if (needs_calculator(text) and hasattr(self._llm, "client") and not bare
                and not (council_turn and os.environ.get("NEIRA_COUNCIL_CALC", "0") == "0")):
            t = time.perf_counter()
            try:
                exprs = []
                for prompt, max_tokens in MATH_ROUTES:
                    r = await self._llm.client.chat.completions.create(
                        model=self._llm.model, temperature=0, max_tokens=max_tokens,
                        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}])
                    exprs.append(r.choices[0].message.content or "")
                note = math_note(*exprs)
                if note:
                    notes.append(note)
                logger.info(f"Dispatcher: math specialists {[e.splitlines()[-1] if e else e for e in exprs]} -> {note[:80]!r}")
            except Exception as e:  # the brain answers without the note
                logger.warning(f"Dispatcher: math specialist failed: {e}")
            timing["math"] = time.perf_counter() - t
        if CALENDAR and CALENDAR.asks_calendar(text) and hasattr(self._llm, "client"):
            t = time.perf_counter()
            try:
                calls = []
                for prompt, max_tokens in CALENDAR.CALENDAR_ROUTES:
                    r = await self._llm.client.chat.completions.create(
                        model=self._llm.model, temperature=0, max_tokens=max_tokens,
                        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}])
                    calls.append(r.choices[0].message.content or "")
                note = CALENDAR.calendar_note(*calls)
                if note:
                    notes.append(note)
                logger.info(f"Dispatcher: calendar {[c.splitlines()[-1] if c else c for c in calls]} -> {note[:80]!r}")
            except Exception as e:
                logger.warning(f"Dispatcher: calendar failed: {e}")
            timing["calendar"] = time.perf_counter() - t
        if not ege and LETTERS and LETTERS.asks_letters(text) and hasattr(self._llm, "client"):
            t = time.perf_counter()
            try:
                calls = []
                for prompt, max_tokens in LETTERS.LETTERS_ROUTES:
                    r = await self._llm.client.chat.completions.create(
                        model=self._llm.model, temperature=0, max_tokens=max_tokens,
                        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}])
                    calls.append(r.choices[0].message.content or "")
                note = LETTERS.letters_note(*calls)
                if note:
                    notes.append(note)
                logger.info(f"Dispatcher: letters {[c.splitlines()[-1] if c else c for c in calls]} -> {note[:80]!r}")
            except Exception as e:
                logger.warning(f"Dispatcher: letters failed: {e}")
            timing["letters"] = time.perf_counter() - t
        for name, _m, asks, routes, note_fn in ORGANS:
            if ege or not (asks(text) and hasattr(self._llm, "client")):
                continue
            t = time.perf_counter()
            try:
                calls = []
                for prompt, max_tokens in routes:
                    r = await self._llm.client.chat.completions.create(
                        model=self._llm.model, temperature=0, max_tokens=max_tokens,
                        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}])
                    calls.append(r.choices[0].message.content or "")
                note = note_fn(*calls)
                if note:
                    notes.append(note)
                logger.info(f"Dispatcher: {name} {[c.splitlines()[-1] if c else c for c in calls]} -> {note[:80]!r}")
            except Exception as e:
                logger.warning(f"Dispatcher: {name} failed: {e}")
            timing[name] = time.perf_counter() - t
        decided = False
        if RUSSKIY and RUSSKIY.asks_russian(text):
            t = time.perf_counter()
            try:
                ans, trace = await asyncio.to_thread(RUSSKIY.russian_answer, text)
                if ans and ans != "0":   # "0": no row fits - more likely a garbled task than a real answer
                    why = ""
                    if RUSSKIY.asks_russian(text) == 9:   # 9-12: the letters row by row, to explain from
                        try:
                            why = await asyncio.to_thread(RUSSKIY.reason_9_12, text, ans)
                        except Exception as e:
                            logger.warning(f"Dispatcher: russkiy reason failed: {e}")
                    notes.append(RUSSKIY.russian_note(ans, why) + EGE_SAY)
                    decided = True
                logger.info(f"Dispatcher: russkiy -> {ans!r} ({trace[:120]})")
            except Exception as e:
                logger.warning(f"Dispatcher: russkiy failed: {e}")
            timing["russkiy"] = time.perf_counter() - t
        if not decided and EGE_ONE and EGE_ONE.is_ege_ru(text):
            t = time.perf_counter()
            try:
                ans = await asyncio.to_thread(EGE_ONE.answer, text)
                if ans:
                    notes.append(f"(Справка органа «ЕГЭ» — задание решено отдельно, с размышлением: ответ {ans}.)"
                                 + EGE_SAY)
                logger.info(f"Dispatcher: ege_one -> {ans!r}")
            except Exception as e:
                logger.warning(f"Dispatcher: ege_one failed: {e}")
            timing["ege_one"] = time.perf_counter() - t
        if council_turn and not ege and hasattr(self._llm, "client"):
            t = time.perf_counter()
            try:
                note, info = await asyncio.to_thread(COUNCIL.solve, text, [n for n in notes if "помнишь" not in n])
                if note and info.get("conclusion"):
                    # the council used the organs' notes and decided; she sees only its conclusion (it had overruled a
                    # wrong calculator note, 24/3+7=15, and she told the author his "arithmetic with hints" was wrong)
                    notes[:] = [n for n in notes if "помнишь" in n or n.startswith("Справка часов")] + [note]
                elif note:
                    notes.append(note)
                logger.info(f"Dispatcher: council -> {info.get('conclusion')!r} ({info.get('confidence')}, "
                            f"thinker {'yes' if info.get('pause') else 'no'})")
            except Exception as e:
                logger.warning(f"Dispatcher: council failed: {e}")
            timing["council"] = time.perf_counter() - t
        if notes:   # the organs are hers: she says "I counted / I checked", never "the note says"
            notes.append(OWN_NOTES)
            part["text"] = text + "\n\n(" + " ".join(notes) + ")"
        timing["dispatch"] = time.perf_counter() - t0
        self._timing = {"turn_start": t0, **timing}
        logger.info("Timing: " + ", ".join(f"{k} {v * 1000:.0f} ms" for k, v in timing.items()))

    async def _check_code(self, text: str) -> None:
        """After her answer: the C blocks in it go through check_code.exe, as in the text chat (all blocks together);
        the result goes to the log. Not wired yet (open questions to the HQ, 04.11): the autofix (more brain calls while
        the voice is back - the voice and the brain do not share the GPU, 29.10) and what she says or shows about it."""
        blocks = CHECK_CODE.extract_c_blocks(text)
        if not blocks:
            return
        code = "\n\n".join(blocks)
        t = time.perf_counter()
        note = await asyncio.to_thread(CHECK_CODE.run_check, code)
        self._last_code_check = {"code": code, "note": note}
        logger.info(f"check_code: {CHECK_CODE.summary(note)} ({len(blocks)} C blocks, {time.perf_counter() - t:.1f} s)")

    async def _remember(self, text: str) -> None:
        """After the answer: a persona-free request writes down lasting facts from the user's words (neira_memory)."""
        try:
            r = await self._llm.client.chat.completions.create(
                model=self._llm.model, temperature=0, max_tokens=150,
                messages=[{"role": "system", "content": _neira_memory.EXTRACT}, {"role": "user", "content": text}])
            facts = _neira_memory.parse_facts(r.choices[0].message.content)
            if facts:
                added = await asyncio.to_thread(NEIRA_MEMORY.add, facts)
                logger.info(f"Memory: remembered {added} (of {facts})")
        except Exception as e:
            logger.warning(f"Memory: could not write down facts: {e}")

    def _to_messages(self, input_data: BatchInput) -> List[Dict[str, Any]]:
        """Prepare messages for LLM API call."""
        messages = self._memory.copy()
        user_content = []
        text_prompt = self._to_text_prompt(input_data)
        if text_prompt:
            user_content.append({"type": "text", "text": text_prompt})

        if input_data.images:
            image_added = False
            for img_data in input_data.images:
                if isinstance(img_data.data, str) and img_data.data.startswith(
                    "data:image"
                ):
                    user_content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": img_data.data, "detail": "auto"},
                        }
                    )
                    image_added = True
                else:
                    logger.error(
                        f"Invalid image data format: {type(img_data.data)}. Skipping image."
                    )

            if not image_added and not text_prompt:
                logger.warning(
                    "User input contains images but none could be processed."
                )

        if user_content:
            user_message = {"role": "user", "content": user_content}
            messages.append(user_message)

            skip_memory = False
            if input_data.metadata and input_data.metadata.get("skip_memory", False):
                skip_memory = True

            if not skip_memory:
                self._add_message(
                    text_prompt if text_prompt else "[User provided image(s)]", "user"
                )
        else:
            logger.warning("No content generated for user message.")

        return messages

    async def _claude_tool_interaction_loop(
        self,
        initial_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> AsyncIterator[Union[str, Dict[str, Any]]]:
        """Handle Claude interaction loop with tool support."""
        messages = initial_messages.copy()
        current_turn_text = ""
        pending_tool_calls = []
        current_assistant_message_content = []

        while True:
            stream = self._llm.chat_completion(messages, self._system, tools=tools)
            pending_tool_calls.clear()
            current_assistant_message_content.clear()

            async for event in stream:
                if event["type"] == "text_delta":
                    text = event["text"]
                    current_turn_text += text
                    yield text
                    if (
                        not current_assistant_message_content
                        or current_assistant_message_content[-1]["type"] != "text"
                    ):
                        current_assistant_message_content.append(
                            {"type": "text", "text": text}
                        )
                    else:
                        current_assistant_message_content[-1]["text"] += text
                elif event["type"] == "tool_use_complete":
                    tool_call_data = event["data"]
                    logger.info(
                        f"Tool request: {tool_call_data['name']} (ID: {tool_call_data['id']})"
                    )
                    pending_tool_calls.append(tool_call_data)
                    current_assistant_message_content.append(
                        {
                            "type": "tool_use",
                            "id": tool_call_data["id"],
                            "name": tool_call_data["name"],
                            "input": tool_call_data["input"],
                        }
                    )
                # elif event["type"] == "message_delta":
                #     if event["data"]["delta"].get("stop_reason"):
                #         stop_reason = event["data"]["delta"].get("stop_reason")
                elif event["type"] == "message_stop":
                    break
                elif event["type"] == "error":
                    logger.error(f"LLM API Error: {event['message']}")
                    yield f"[Error from LLM: {event['message']}]"
                    return

            if pending_tool_calls:
                filtered_assistant_content = [
                    block
                    for block in current_assistant_message_content
                    if not (
                        block.get("type") == "text"
                        and not block.get("text", "").strip()
                    )
                ]

                if filtered_assistant_content:
                    messages.append(
                        {"role": "assistant", "content": filtered_assistant_content}
                    )
                    assistant_text_for_memory = "".join(
                        [
                            c["text"]
                            for c in filtered_assistant_content
                            if c["type"] == "text"
                        ]
                    ).strip()
                    if assistant_text_for_memory:
                        self._add_message(assistant_text_for_memory, "assistant")

                tool_results_for_llm = []
                if not self._tool_executor:
                    logger.error(
                        "Claude Tool interaction requested but ToolExecutor is not available."
                    )
                    yield "[Error: ToolExecutor not configured]"
                    return

                tool_executor_iterator = self._tool_executor.execute_tools(
                    tool_calls=pending_tool_calls,
                    caller_mode="Claude",
                )
                try:
                    while True:
                        update = await anext(tool_executor_iterator)
                        if update.get("type") == "final_tool_results":
                            tool_results_for_llm = update.get("results", [])
                            break
                        else:
                            yield update
                except StopAsyncIteration:
                    logger.warning(
                        "Tool executor finished without final results marker."
                    )

                if tool_results_for_llm:
                    messages.append({"role": "user", "content": tool_results_for_llm})

                # stop_reason = None
                continue
            else:
                if current_turn_text:
                    self._add_message(current_turn_text, "assistant")
                return

    async def _openai_tool_interaction_loop(
        self,
        initial_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> AsyncIterator[Union[str, Dict[str, Any]]]:
        """Handle OpenAI interaction with tool support."""
        messages = initial_messages.copy()
        current_turn_text = ""
        pending_tool_calls: Union[List[ToolCallObject], List[Dict[str, Any]]] = []
        current_system_prompt = self._system

        while True:
            if self.prompt_mode_flag:
                if self._mcp_prompt_string:
                    current_system_prompt = (
                        f"{self._system}\n\n{self._mcp_prompt_string}"
                    )
                else:
                    logger.warning("Prompt mode active but mcp_prompt_string is empty!")
                    current_system_prompt = self._system
                tools_for_api = None
            else:
                current_system_prompt = self._system
                tools_for_api = tools

            stream = self._llm.chat_completion(
                messages, current_system_prompt, tools=tools_for_api
            )
            pending_tool_calls.clear()
            current_turn_text = ""
            assistant_message_for_api = None
            detected_prompt_json = None
            goto_next_while_iteration = False

            async for event in stream:
                if self.prompt_mode_flag:
                    if isinstance(event, str):
                        current_turn_text += event
                        if self._json_detector:
                            potential_json = self._json_detector.process_chunk(event)
                            if potential_json:
                                try:
                                    if isinstance(potential_json, list):
                                        detected_prompt_json = potential_json
                                    elif isinstance(potential_json, dict):
                                        detected_prompt_json = [potential_json]

                                    if detected_prompt_json:
                                        break
                                except Exception as e:
                                    logger.error(f"Error parsing detected JSON: {e}")
                                    if self._json_detector:
                                        self._json_detector.reset()
                                    yield f"[Error parsing tool JSON: {e}]"
                                    goto_next_while_iteration = True
                                    break
                        yield event
                else:
                    if isinstance(event, str):
                        current_turn_text += event
                        yield event
                    elif isinstance(event, list) and all(
                        isinstance(tc, ToolCallObject) for tc in event
                    ):
                        pending_tool_calls = event
                        assistant_message_for_api = {
                            "role": "assistant",
                            "content": current_turn_text if current_turn_text else None,
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": tc.type,
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for tc in pending_tool_calls
                            ],
                        }
                        break
                    elif event == "__API_NOT_SUPPORT_TOOLS__":
                        logger.warning(
                            f"LLM {getattr(self._llm, 'model', '')} has no native tool support. Switching to prompt mode."
                        )
                        self.prompt_mode_flag = True
                        if self._tool_manager:
                            self._tool_manager.disable()
                        if self._json_detector:
                            self._json_detector.reset()
                        goto_next_while_iteration = True
                        break
            if goto_next_while_iteration:
                continue

            if detected_prompt_json:
                logger.info("Processing tools detected via prompt mode JSON.")
                self._add_message(current_turn_text, "assistant")

                parsed_tools = self._tool_executor.process_tool_from_prompt_json(
                    detected_prompt_json
                )
                if parsed_tools:
                    tool_results_for_llm = []
                    if not self._tool_executor:
                        logger.error(
                            "Prompt Tool interaction requested but ToolExecutor/MCPClient is not available."
                        )
                        yield "[Error: ToolExecutor/MCPClient not configured for prompt mode]"
                        continue

                    tool_executor_iterator = self._tool_executor.execute_tools(
                        tool_calls=parsed_tools,
                        caller_mode="Prompt",
                    )
                    try:
                        while True:
                            update = await anext(tool_executor_iterator)
                            if update.get("type") == "final_tool_results":
                                tool_results_for_llm = update.get("results", [])
                                break
                            else:
                                yield update
                    except StopAsyncIteration:
                        logger.warning(
                            "Prompt mode tool executor finished without final results marker."
                        )

                    if tool_results_for_llm:
                        result_strings = [
                            res.get("content", "Error: Malformed result")
                            for res in tool_results_for_llm
                        ]
                        combined_results_str = "\n".join(result_strings)
                        messages.append(
                            {"role": "user", "content": combined_results_str}
                        )
                continue

            elif pending_tool_calls and assistant_message_for_api:
                messages.append(assistant_message_for_api)
                if current_turn_text:
                    self._add_message(current_turn_text, "assistant")

                tool_results_for_llm = []
                if not self._tool_executor:
                    logger.error(
                        "OpenAI Tool interaction requested but ToolExecutor/MCPClient is not available."
                    )
                    yield "[Error: ToolExecutor/MCPClient not configured for OpenAI mode]"
                    continue

                tool_executor_iterator = self._tool_executor.execute_tools(
                    tool_calls=pending_tool_calls,
                    caller_mode="OpenAI",
                )
                try:
                    while True:
                        update = await anext(tool_executor_iterator)
                        if update.get("type") == "final_tool_results":
                            tool_results_for_llm = update.get("results", [])
                            break
                        else:
                            yield update
                except StopAsyncIteration:
                    logger.warning(
                        "OpenAI tool executor finished without final results marker."
                    )

                if tool_results_for_llm:
                    messages.extend(tool_results_for_llm)
                continue

            else:
                if current_turn_text:
                    self._add_message(current_turn_text, "assistant")
                return

    def _chat_function_factory(
        self,
    ) -> Callable[[BatchInput], AsyncIterator[Union[SentenceOutput, Dict[str, Any]]]]:
        """Create the chat pipeline function."""

        @tts_filter(self._tts_preprocessor_config)
        @display_processor()
        @actions_extractor(self._live2d_model)
        @gramota_filter()
        @sentence_divider(
            faster_first_response=self._faster_first_response,
            segment_method=self._segment_method,
            valid_tags=["think"],
        )
        async def chat_with_memory(
            input_data: BatchInput,
        ) -> AsyncIterator[Union[str, Dict[str, Any]]]:
            """Process chat with memory and tools."""
            self.reset_interrupt()
            self.prompt_mode_flag = False

            messages = self._to_messages(input_data)
            # Sequential mode (29.10, the author's choice): the voice and the brain never share the GPU - with a game
            # running they did not fit, and the brain fell to 1-2 tokens/s. The voice parks (0.3 s) for every turn,
            # the brain writes the whole answer alone, then the voice comes back (0.1 s) and speaks it: ~3-5 s later
            # start. A hard turn first says Neira needs to think. Smart mode: an ordinary turn parks only when free VRAM
            # is below NEIRA_TIGHT_MIB (voice_swap.tight). NEIRA_VOICE_SEQUENTIAL=0: park on hard turns only.
            parked = False
            council_turn = False
            if VOICE_SWAP and await asyncio.to_thread(VOICE_SWAP.voice_up):
                last = messages[-1] if messages else {}
                utext = next((p.get("text", "") for p in last.get("content", []) if isinstance(p, dict)
                              and p.get("type") == "text"), "") if isinstance(last.get("content"), list) else ""
                t = time.perf_counter()
                council_turn = bool(last.get("role") == "user" and COUNCIL and not direct_math(perceive(utext))
                                    and COUNCIL.needs_council(perceive(utext)))
                if last.get("role") == "user" and (VOICE_SWAP.is_hard(utext, RUSSKIY)
                                                   or (EGE_ONE and EGE_ONE.is_ege_ru(utext))):
                    before = await asyncio.to_thread(VOICE_SWAP.served)
                    yield VOICE_SWAP.warning() + " "   # spoken before the voice leaves
                    parked = await VOICE_SWAP.unload(before)
                # 29.10, the author: always write the whole answer first, then speak - the voice never shares the GPU
                # with the brain; NEIRA_VOICE_ALWAYS_PARK=0 goes back to the smart mode (park only when VRAM is short)
                elif council_turn or (os.environ.get("NEIRA_VOICE_SEQUENTIAL", "1") != "0"
                                      and (os.environ.get("NEIRA_VOICE_ALWAYS_PARK", "1") != "0"
                                           or await asyncio.to_thread(VOICE_SWAP.tight))):
                    parked = await VOICE_SWAP.park_now()   # a council turn always: the council needs the GPU
                logger.info(f"Voice swap: parked {parked} ({time.perf_counter() - t:.1f} s)")
            # plan step 15, the author's rule: an answer not ready in WAIT_S seconds gets a "give me a minute" line
            # (a ready phrase: instant, even with the voice parked); no warning up front for the council - it is
            # often done in ~5 s
            dispatch = asyncio.create_task(self._dispatch(messages))
            if parked and VOICE_SWAP:
                done, _ = await asyncio.wait({dispatch}, timeout=float(os.environ.get("NEIRA_WAIT_S", "15")))
                if not done:
                    yield VOICE_SWAP.waiting() + " "
            await dispatch
            held = []   # the answer, kept while the voice is parked

            async def voice_back():
                nonlocal parked
                if parked:
                    t = time.perf_counter()
                    ok = await VOICE_SWAP.load()
                    parked = False
                    logger.info(f"Voice swap: voice back {ok} ({time.perf_counter() - t:.1f} s), {len(held)} pieces")
            tools = None
            tool_mode = None
            llm_supports_native_tools = False

            if self._use_mcpp and self._tool_manager:
                tools = None
                if isinstance(self._llm, ClaudeAsyncLLM):
                    tool_mode = "Claude"
                    tools = self._formatted_tools_claude
                    llm_supports_native_tools = True
                elif isinstance(self._llm, OpenAICompatibleAsyncLLM):
                    tool_mode = "OpenAI"
                    tools = self._formatted_tools_openai
                    llm_supports_native_tools = True
                else:
                    logger.warning(
                        f"LLM type {type(self._llm)} not explicitly handled for tool mode determination."
                    )

                if llm_supports_native_tools and not tools:
                    logger.warning(
                        f"No tools available/formatted for '{tool_mode}' mode, despite MCP being enabled."
                    )

            if self._use_mcpp and tool_mode == "Claude":
                logger.debug(
                    f"Starting Claude tool interaction loop with {len(tools)} tools."
                )
                async for output in self._claude_tool_interaction_loop(
                    messages, tools if tools else []
                ):
                    yield output
                return
            elif self._use_mcpp and tool_mode == "OpenAI":
                logger.debug(
                    f"Starting OpenAI tool interaction loop with {len(tools)} tools."
                )
                answer_text = ""   # her words, for the check_code organ
                async for output in self._openai_tool_interaction_loop(
                    messages, tools if tools else []
                ):
                    if isinstance(output, str):
                        answer_text += output
                    if parked:
                        held.append(output)
                    else:
                        yield output
                await voice_back()
                for output in held:
                    yield output
                if NEIRA_MEMORY and self._turn_text:   # the brain is free now: write down what was learned
                    asyncio.create_task(self._remember(self._turn_text))
                if CHECK_CODE and "```" in answer_text:
                    asyncio.create_task(self._check_code(answer_text))
                return
            else:
                logger.info("Starting simple chat completion.")
                token_stream = self._llm.chat_completion(messages, self._system)
                complete_response = ""
                async for event in token_stream:
                    text_chunk = ""
                    if isinstance(event, dict) and event.get("type") == "text_delta":
                        text_chunk = event.get("text", "")
                    elif isinstance(event, str):
                        text_chunk = event
                    else:
                        continue
                    if text_chunk:
                        if parked:
                            held.append(text_chunk)
                        else:
                            yield text_chunk
                        complete_response += text_chunk
                await voice_back()
                for text_chunk in held:
                    yield text_chunk
                if complete_response:
                    self._add_message(complete_response, "assistant")
                if CHECK_CODE and "```" in complete_response:
                    asyncio.create_task(self._check_code(complete_response))

        return chat_with_memory

    async def chat(
        self,
        input_data: BatchInput,
    ) -> AsyncIterator[Union[SentenceOutput, Dict[str, Any]]]:
        """Run chat pipeline."""
        chat_func_decorated = self._chat_function_factory()
        async for output in chat_func_decorated(input_data):
            yield output

    def reset_interrupt(self) -> None:
        """Reset interrupt flag."""
        self._interrupt_handled = False

    def start_group_conversation(
        self, human_name: str, ai_participants: List[str]
    ) -> None:
        """Start a group conversation."""
        if not self._tool_prompts:
            logger.warning("Tool prompts dictionary is not set.")
            return

        other_ais = ", ".join(name for name in ai_participants)
        prompt_name = self._tool_prompts.get("group_conversation_prompt", "")

        if not prompt_name:
            logger.warning("No group conversation prompt name found.")
            return

        try:
            group_context = prompt_loader.load_util(prompt_name).format(
                human_name=human_name, other_ais=other_ais
            )
            self._memory.append({"role": "user", "content": group_context})
        except FileNotFoundError:
            logger.error(f"Group conversation prompt file not found: {prompt_name}")
        except KeyError as e:
            logger.error(f"Missing formatting key in group conversation prompt: {e}")
        except Exception as e:
            logger.error(f"Failed to load group conversation prompt: {e}")
