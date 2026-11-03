# -*- coding: utf-8 -*-
"""Динамичный характер Нейры: правила поведения, накопленные из разговоров.

Как это работает:
- пользователь говорит что-то вроде «не обрывайся», «никогда так не делай»,
  «всегда дописывай код» — скрипт распознаёт это как просьбу о поведении;
- правило сохраняется в neira_behavior_rules.json и добавляется к системному
  промпту при каждом следующем сообщении;
- «забудь правило ...» — удаляет правило; «покажи правила» — показывает список.

Хранение: простой JSON-список строк (порядок = порядок добавления).
"""
import json
import os
import re

RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "neira_behavior_rules.json")

# Фразы-маркеры, указывающие на просьбу об изменении поведения.
# Порядок важен: сначала длинные/конкретные, потом короткие.
_BEHAVIOR_PATTERNS = [
    (re.compile(r"(?:никогда|больше|дальше|впредь)\s+(?:так\s+)?не\s+(.+)",
                re.I), "никогда не {0}"),
    (re.compile(r"(?:не\s+обрывайся|не\s+обрывай|не\s+бросай|не\s+останавливайся)(.*)",
                re.I), "никогда не обрывайся на полуслове, всегда доводи ответ до конца"),
    (re.compile(r"(?:всегда|постоянно|впредь)\s+(.+)", re.I), "всегда {0}"),
    (re.compile(r"(?:пожалуйста\s+)?(?:перестань|прекрати|хватит)\s+(.+)",
                re.I), "не {0}"),
    (re.compile(r"не\s+(делай\s+)?(так|этого|подобного)(.*)", re.I),
     "не делай так, как я прошу не делать (смотри просьбы пользователя)"),
]

# Слова-подсказки: сообщение содержит поведенческую просьбу, только если
# есть одно из этих слов + глагол. Защита от ложных срабатываний.
_HINT = re.compile(r"не|никогда|всегда|перестань|прекрати|хватит|обрывай|бросай|"
                   r"дописывай|умалчивай|недосказывай|разговаривай|отвечай", re.I)


def load_rules():
    if not os.path.exists(RULES_FILE):
        return []
    try:
        rules = json.load(open(RULES_FILE, encoding="utf-8"))
        return [r for r in rules if isinstance(r, str) and r.strip()]
    except Exception:
        return []


def save_rules(rules):
    tmp = RULES_FILE + ".tmp"
    json.dump(rules, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    os.replace(tmp, RULES_FILE)


def extract_rule(text):
    """Достать правило из просьбы пользователя. None — если это не просьба о поведении."""
    if not text or not _HINT.search(text):
        return None
    # просьба о поведении — короткая реплика в одну строку; во вставленном ТЗ
    # «всегда/никогда» описывают задачу, а не Нейру (03.11: «всегда печатать знак
    # для неотрицательных» из ТЗ по sprintf стало правилом)
    if "\n" in text.strip() or len(text) > 200:
        return None
    best = None
    for pattern, template in _BEHAVIOR_PATTERNS:
        m = pattern.search(text)
        if m and (best is None or len(m.group(0)) > len(best[0])):
            best = (m.group(0), template, m)
    if best is None:
        return None
    raw, template, m = best
    # защита от мусора: «всегда …» с длинным хвостом (например, фрагмент текста
    # задачи) не должен становиться правилом поведения
    if len(raw) > 200:
        return None
    # для шаблонов с подстановкой — только захваченный хвост, без слова-маркера
    # (раньше «всегда отвечай» давало «всегда всегда отвечай», 03.11)
    filled = template.format(m.group(1).strip()) if "{0}" in template and m.groups() else template
    return filled.strip(" .,;:!?")


def forget_rule(text, rules):
    """«забудь правило ...» — удалить правило, содержащее эту фразу."""
    m = re.search(r"забудь\s+(?:правило\s+)?(.+)", text, re.I)
    if not m:
        return rules, False
    frag = m.group(1).strip().lower().strip(" .,;:!?")
    new_rules = [r for r in rules if frag not in r.lower()]
    return new_rules, len(new_rules) != len(rules)


def add_rule(text, rules):
    rule = extract_rule(text)
    if not rule:
        return rules, False
    if rule not in rules:
        rules.append(rule)
        save_rules(rules)
        return rules, True
    return rules, False


def build_system_prompt(persona, rules):
    if not rules:
        return persona
    block = "\n".join(f"- {r}" for r in rules)
    return persona + "\n\nПравила поведения, которые ты обязана соблюдать (пользователь просил):\n" + block
