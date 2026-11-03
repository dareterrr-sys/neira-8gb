"""Stylistic filter (31.10, the author: «научить её разговаривать как человек, а не как автобот»): officialese
(«канцелярит») by D. E. Rozental, «Справочник по русскому языку. Практическая стилистика» (§ 18 canzeleryisms and
clichés, § 56 the split predicate, § 84 stacked cases, § 100 verbal nouns) + assistant clichés of modern chat
models (not in Rozental: his book predates them). Code, not a model: pymorphy3 morphology and word lists.
check(text) -> {"score": problems per 100 words, "words": n, "hits": [(kind, fragment, hint)]}
Usage: python stil.py "текст"   |   python stil.py --file text.txt"""
import re
import sys
from functools import lru_cache

import pymorphy3

MORPH = pymorphy3.MorphAnalyzer()
WORD = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*")

# § 56: a semi-empty verb + a verbal noun instead of one verb («оказать помощь» = «помочь»)
EMPTY_VERBS = {"оказывать", "оказать", "производить", "произвести", "осуществлять", "осуществить", "проводить",
               "провести", "проявлять", "проявить", "совершать", "совершить", "наносить", "нанести", "вести",
               "подвергать", "подвергнуть", "принимать", "принять", "давать", "дать", "иметь", "идти", "происходить",
               "произойти", "являться", "добиться", "добиваться", "выполнять", "выполнить", "обеспечивать",
               "обеспечить", "использовать", "применять", "брать", "взять", "питать", "предпринимать", "предпринять"}
# set phrases that are normal Russian, not a split predicate
SPLIT_OK = {("принимать", "решение"), ("принять", "решение"), ("давать", "обещание"), ("дать", "обещание"),
            ("иметь", "значение"), ("вести", "себя"), ("принимать", "участие"), ("принять", "участие")}
VERBAL_NOUN = re.compile(r"(ание|ение|ятие|утие|ация|яция|ование|ирование)$")
# words on -ние that are ordinary objects/feelings, not an action (§ 100.2: terms and results are fine)
NOUN_OK = {"здание", "знание", "мнение", "время", "внимание", "желание", "задание", "занятие", "издание", "имение",
           "кушание", "настроение", "отношение", "поколение", "положение", "понятие", "предложение", "предприятие",
           "растение", "расстояние", "сознание", "сочинение", "состояние", "стихотворение", "течение", "упражнение",
           "учение", "чувство", "явление", "значение", "выражение", "впечатление", "мероприятие", "собрание",
           "образование", "событие", "решение", "удовольствие", "приключение", "воспоминание", "название",
           "окружение", "ощущение", "общение", "свидание", "отделение", "сражение", "варенье", "печенье",
           "умение", "терпение", "мгновение", "направление", "объявление", "приглашение", "правление", "население",
           "вдохновение", "сомнение", "уважение", "волнение", "движение", "зрение", "мышление", "питание",
           "поведение", "воображение", "происхождение", "существование", "ранение", "здоровье", "сообщение",
           "приложение", "описание", "расписание", "условие", "дыхание", "молчание", "наказание", "обещание",
           "признание", "свидетельство", "строение", "освещение", "угощение", "украшение", "жилище"}
# § 18 and § 79: officialese words and «new prepositions»
OFFICIAL = [
    (r"\bв целях\b", "в целях → чтобы"), (r"\bв рамках\b", "в рамках → в, при"), (r"\bв части\b", "в части → о, по"),
    (r"\bпо линии\b", "по линии → (переписать)"), (r"\bв деле\b", "в деле → (переписать)"),
    (r"\bв силу\b(?! закона| привычки| обстоятельств)", "в силу → из-за, потому что"),
    (r"\bза сч[её]т\b", "за счёт → благодаря, тем, что"), (r"\bимеет место\b|\bимели место\b|\bимело место\b",
                                                          "имеет место → есть, бывает"),
    (r"\bна (сегодняшний|данный) (день|момент)\b", "на сегодняшний день → сейчас"),
    (r"\bв настоящее время\b", "в настоящее время → сейчас"), (r"\bв связи с тем,? что\b", "в связи с тем что → потому что"),
    (r"\bввиду\b|\bвследствие\b|\bпо причине\b", "ввиду / вследствие → из-за"), (r"\bс целью\b", "с целью → чтобы"),
    (r"\bпутём\b|\bпутем\b", "путём → (глагол или деепричастие)"), (r"\bпосредством\b", "посредством → через, с помощью"),
    (r"\bв ходе\b", "в ходе → во время, пока"), (r"\bв процессе\b", "в процессе → пока, во время"),
    (r"\bкасательно\b|\bотносительно\b", "касательно → о, про"), (r"\bвышеуказанн\w*|\bнижеследующ\w*", "(канцелярия)"),
    # singular only: «данные / данных» is mostly the noun «data» (31.10: 13 of 15 Neira's hits were «данные»)
    (r"\bданн(ый|ая|ое|ого|ой|ому|ым|ую)\b", "данный → этот"),
    (r"\bявля(ется|ются|лся|лась|лось|лись|ясь|ющ\w*)\b", "является → (тире или «это»)"),
    (r"\bосуществл\w+", "осуществлять → делать, вести"), (r"\bфункционир\w+", "функционировать → работать"),
    (r"\bвыступа(ет|ют|л|ла|ло|ли) в (качестве|роли)\b", "выступает в качестве → служит, это"),
    (r"\bв качестве\b", "в качестве → как"), (r"\bпо отношению к\b", "по отношению к → к"),
    (r"\bв плане\b", "в плане → (переписать)"), (r"\bсо стороны\b", "со стороны → (кто делает)"),
    (r"\bв обязательном порядке\b", "в обязательном порядке → обязательно"),
    (r"\bнеобходимо\b|\bнеобходимость\w*", "необходимо → нужно, надо"),
]
# § 18: clichés and «paired words» (слова-спутники)
CLICHES = [
    r"неизгладим\w+ впечатлени\w+", r"целый ряд", r"сравнительно небольш\w+", r"игра(ет|ют|л|ла|ли|ть) (важную|ключевую|огромную|большую) роль",
    r"широк\w+ спектр\w*", r"во главу угла", r"под углом зрения", r"не мог\w* не",
    r"(огромн|колоссальн)\w+ значени\w+", r"(является|являются) неотъемлем\w+ част\w+", r"неотъемлем\w+ част\w+",
    r"в современном мире", r"в наше время", r"уникальн\w+ возможност\w+", r"богат\w+ (истори|наследи)\w+",
    r"(горяч|тёпл|тепл)\w+ поддержк\w+", r"(резк|острой|острая) критик\w+", r"красной нитью",
]
# modern assistant clichés: the «autobot» register (not Rozental)
BOT = [
    r"^\s*(конечно|разумеется|безусловно)!",   # «Конечно, …» in a dialogue is ordinary speech r"отличн\w+ вопрос", r"хорош\w+ вопрос", r"интересн\w+ вопрос",
    r"важно (отметить|понимать|помнить|учитывать|подчеркнуть)", r"стоит (отметить|упомянуть|подчеркнуть)",
    r"следует (отметить|подчеркнуть|учитывать)", r"давай(те)? разбер[её]мся", r"надеюсь,? (это|мой ответ) (помо|поможет|был)",
    r"если у (тебя|вас) (есть|остались|появятся) (ещё |еще )?вопрос", r"обращайся|обращайтесь", r"рад(а)? помочь",
    r"в целом,", r"в заключени\w+", r"подводя итог", r"таким образом,", r"с одной стороны.{0,80}с другой стороны",
    r"как (ИИ|искусственный интеллект|языковая модель)", r"я (всего лишь|просто) (ИИ|программа|модель)",
    r"не стесняйся", r"чем (ещё|еще) (могу|я могу) помочь", r"вот (несколько|некоторые) (способов|советов|вариантов|идей)",
]
KINDS = {"split": "расщеплённое сказуемое", "chain": "нанизывание падежей", "nouns": "отглагольные существительные",
         "official": "канцеляризм", "cliche": "штамп", "bot": "ИИ-штамп"}


@lru_cache(maxsize=50000)
def parse(w):
    return MORPH.parse(w.lower())


def is_verbal_noun(w):
    p = parse(w)[0]
    n = p.normal_form
    return "NOUN" in p.tag and bool(VERBAL_NOUN.search(n)) and n not in NOUN_OK and len(n) > 6


def tokens(text):
    return [(m.group(0), m.start(), m.end()) for m in WORD.finditer(text)]


def split_predicates(toks, text):
    """§ 56: an empty verb and a verbal noun within three words: «оказывает помощь», «произвёл опробование»."""
    hits = []
    for i, (w, s, _) in enumerate(toks):
        p = parse(w)[0]
        if not ({"VERB", "INFN", "PRTF", "PRTS", "GRND"} & set(str(p.tag).replace(" ", ",").split(","))):
            continue
        lemma = p.normal_form
        if lemma not in EMPTY_VERBS:
            continue
        for w2, _, e2 in toks[i + 1:i + 4]:
            # the noun must be the verb's object («оказать помощь», «добиться пересиления») or, for «идёт / происходит»,
            # its subject («идёт снижение»): not any noun nearby («выполнен вследствие неимения»)
            want = {"идти": "nomn", "происходить": "nomn", "произойти": "nomn", "добиться": "gent", "добиваться": "gent",
                    "подвергать": "datv", "подвергнуть": "datv"}.get(lemma, "accs")
            # any reading: «опробование» is nominative and accusative alike, pymorphy lists nominative first
            if is_verbal_noun(w2) and any(q.tag.case == want for q in parse(w2) if "NOUN" in q.tag) and (lemma, parse(w2)[0].normal_form) not in SPLIT_OK:
                hits.append(("split", text[s:e2], f"«{lemma} {parse(w2)[0].normal_form}» → один глагол"))
                break
    return hits


def case_chains(toks, text):
    """§ 84: three or more nouns in a row in the genitive (adjectives between them allowed); two instrumentals."""
    hits = []
    run, start, prev = [], None, 0
    for w, s, e in toks + [("", len(text), len(text))]:
        if run and text[prev:s].strip():   # a comma or a bracket between: an enumeration, not a chain
            if len(run) >= 4:
                hits.append(("chain", text[start:run[-1][1]], f"{len(run)} родительных подряд → разбить, заменить глаголом"))
            run, start = [], None
        prev = e
        ps = parse(w) if w else []
        # the reading: take the first parse - the ambiguity of «дома» (gen/nom pl) is accepted as noise
        tag = ps[0].tag if ps else None
        gen_noun = tag is not None and "NOUN" in tag and "gent" in tag
        gen_adj = tag is not None and ({"ADJF", "PRTF", "NPRO"} & {tag.POS}) and "gent" in tag
        if gen_noun:
            run.append((s, e))
            start = start if start is not None else s
        elif gen_adj and run:
            continue
        elif gen_adj and not run:
            start = s if start is None else start
        else:
            if len(run) >= 4:   # Rozental's examples are 4-5 long; 3 is ordinary («лекции профессора Кайданова»)
                hits.append(("chain", text[start:run[-1][1]], f"{len(run)} родительных подряд → разбить, заменить глаголом"))
            run, start = [], None
    # two instrumentals side by side: «разрешён назначенной дирекцией комиссией»
    for (w1, s1, e1), (w2, s2, e2) in zip(toks, toks[1:]):
        if text[e1:s2].strip():
            continue
        t1, t2 = parse(w1)[0].tag, parse(w2)[0].tag
        if "NOUN" in t1 and "NOUN" in t2 and "ablt" in t1 and "ablt" in t2 and not ({"Name", "Surn", "Patr"} & (t1.grammemes | t2.grammemes)):
            hits.append(("chain", text[s1:e2], "два творительных подряд → «которую назначила дирекция»"))
    return hits


def check(text):
    toks = tokens(text)
    n = max(len(toks), 1)
    hits = split_predicates(toks, text) + case_chains(toks, text)
    low = text.lower()
    for pat, hint in OFFICIAL:
        for m in re.finditer(pat, low):
            hits.append(("official", text[m.start():m.end()], hint))
    for pat in CLICHES:
        for m in re.finditer(pat, low):
            hits.append(("cliche", text[m.start():m.end()], "штамп → сказать конкретно"))
    for pat in BOT:
        for m in re.finditer(pat, low, re.M):
            hits.append(("bot", text[m.start():m.end()], "ИИ-штамп → убрать или сказать по-человечески"))
    vn = [w for w, _, _ in toks if is_verbal_noun(w)]
    if len(vn) >= 3 and len(vn) / n > 0.06:   # § 100: verbal nouns crowd the text (> 6 per 100 words)
        hits.append(("nouns", ", ".join(vn[:6]), f"{len(vn)} на {n} слов → глаголы вместо -ание/-ение"))
    return {"score": round(100 * len(hits) / n, 1), "words": n, "hits": hits}


def show(text):
    r = check(text)
    print(f"канцелярит: {r['score']} на 100 слов ({len(r['hits'])} мест, {r['words']} слов)")
    for kind, frag, hint in r["hits"]:
        print(f"  [{KINDS[kind]}] «{frag}» — {hint}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] == ["--file"]:
        show(open(sys.argv[2], encoding="utf-8").read())
    else:
        show(" ".join(sys.argv[1:]))
