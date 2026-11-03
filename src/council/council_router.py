"""Which live turns go to the council (29.10, plan step 15): a task to solve or a fact to recall - not chat with Neira
herself, not a request for a story or code. Rules, not a model call: every live turn passes here, so it must cost
nothing. Measured by router_eval below on the question sets (should go) and the author's real messages (should not).
EGE Russian tasks are caught earlier (their own organs), so they never reach this."""
import re

# talking to/about Neira herself: her opinions, feelings, plans, abilities - chat, not a task
PERSONAL = re.compile(r"\b(ты|тебя|тебе|тобой|твой|твоя|твоё|твое|твои|твоих|твоим|вы|вас|вам|сама|самой)\b", re.I)
# a task: a count, a puzzle, a syllogism, a comparison, a trap
TASK = re.compile(r"сколько|во сколько|найди|найдите|посчитай|вычисли|реши\b|решите|определи|какой (?:по счёту|день)|"
                  r"следует ли|верно ли|правда ли|можно ли|если\b.*\?|кто из|что тяжелее|что больше|что быстрее|"
                  r"больше или меньше|загадк|подвох|сколько раз|за сколько|какова|каков|чему равн|"
                  r"все\s+\w+\s*[—–-]|некоторые\s+\w+|ни один\b|как зовут|каким\b.*\bстал|что упад|на какую|"
                  r"какую цифру|продолжи|последовательност|какое следующ|куда\b|у кого|кто прав|чей\b|чья\b|"
                  r"сколько.*\?", re.I | re.S)
# code and programs: a request to the brain itself, not a puzzle («а если 10 чисел вводит с клавиатуры?»)
CODE = re.compile(r"функци|код\b|кода\b|программ|клавиатур|\bmain\b|мейн|питон|python|c\+\+|массив", re.I)
# a fact to recall (the council's erudition branch: the «не знаю» vector and the doubt sensor)
FACT = re.compile(r"^(?:а\s+)?(?:кто|когда|где|в каком году|какой|какая|какое|какие|каким|чем|почему|зачем|откуда|"
                  r"сколько|что такое|что значит|из чего|как называ)\b", re.I)
REQUEST = re.compile(r"\b(расскажи|напиши|сочини|придумай|спой|покажи|переведи|давай|помоги)\b", re.I)


def needs_council(text):
    """text: as the dispatcher sees it - numbers in words already digits (perception)."""
    t = (text or "").strip()
    if len(t) < 12 or CODE.search(t):
        return False
    has_digits = bool(re.search(r"\d", t))
    if TASK.search(t) and (has_digits or "?" in t or len(t) > 60):
        # «ты» in a task is usually the reader («у тебя 3 яблока») - a task wins over personal when it has numbers
        return has_digits or not PERSONAL.search(t)
    if FACT.search(t) and "?" in t and not PERSONAL.search(t) and not REQUEST.search(t):
        return True
    # a long question with numbers is a word problem even without a cue word («Автобус ехал ... 60 км/ч ...?»)
    if has_digits and len(t) > 60 and "?" in t and not REQUEST.search(t):
        return True
    # a riddle: a question of a sentence or more, not about Neira, not a request («Сын врача не приходится врачу
    # сыном. Кем врач приходится мальчику?»)
    return len(t) >= 40 and t.rstrip().endswith("?") and not PERSONAL.search(t) and not REQUEST.search(t)


def router_eval():
    import json
    import os
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(here))
    from perception import numbers_to_digits as perceive
    for name in ("hard_questions", "work3_questions", "work2_questions", "mgsm_ru_questions", "work_questions"):
        qs = json.load(open(os.path.join(here, name + ".json"), encoding="utf-8"))
        miss = [q for q in qs if not needs_council(perceive(q["q"]))]
        print(f"{name:20s} sent {len(qs) - len(miss)}/{len(qs)}" +
              (f"   missed e.g.: {[m['q'][:60] for m in miss[:3]]}" if miss else ""))
    chat = json.load(open(os.path.join(here, "chat_user_msgs.json"), encoding="utf-8"))
    sent = [m for m in chat if needs_council(perceive(m))]
    print(f"author's chat        sent {len(sent)}/{len(chat)}: {sent}")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    router_eval()
