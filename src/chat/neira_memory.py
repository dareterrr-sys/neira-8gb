"""Neira's long-term memory, triggered like a human's (the user's idea): a cue in what you say brings up what she knows.

- remember: after a turn, a persona-free request to the brain writes down lasting facts from the user's words; each fact is
  stored with its "cipher" (an e5-small embedding, ~5 ms on the CPU) in facts.jsonl.
- recall: every user turn is encoded too; a fact comes up only when it beats a set of neutral background sentences by a
  margin (e5 similarities all sit in 0.78-0.89, so a fixed threshold recalled "аниме-сериал" on "Привет!").
Neira never calls a tool for this: the dispatcher in Open-LLM-VTuber (basic_memory_agent.py) does both.
"""
import json
import os
import threading
import time

import torch
from transformers import AutoModel, AutoTokenizer

MODEL_DIR = os.environ.get("NEIRA_EMBED", r"D:\AI\models\multilingual-e5-small")
FACTS = os.environ.get("NEIRA_FACTS", r"D:\AI\neira-memory\facts.jsonl")
MARGIN = 0.012        # a fact must beat the best background sentence by this much (tuned on 12 cues, 2026-10-20)
SAME = 0.95           # a new fact this close to a stored one is a repeat
BACKGROUND = ["Погода бывает разной", "Люди любят поговорить", "У каждого есть свои дела", "Вчера был обычный день",
              "Иногда хочется отдохнуть", "Еда бывает вкусной", "В мире много интересного", "Время идёт быстро",
              "Бывают хорошие и плохие новости", "Музыка поднимает настроение", "Компьютеры есть почти у всех",
              "Учёба требует сил"]
EXTRACT = (
    "Ты ведёшь записную книжку о человеке, который говорит с тобой. Из его реплики выпиши новые УСТОЙЧИВЫЕ факты о нём "
    "самом: имя, учёба, работа, увлечения, вкусы, планы, важные события, близкие люди и питомцы, его компьютер. Каждый "
    "факт — короткой фразой без подлежащего (например: «Учится в Школе 21», «Есть кот Барсик»), по одному на строку, без "
    "нумерации. Не записывай сиюминутное (настроение, что делает прямо сейчас), выводы о характере по одному случаю, "
    "вопросы и общие рассуждения. Если фактов нет, ответь словом НЕТ.")


class Memory:
    def __init__(self, model_dir=MODEL_DIR, path=FACTS):
        self.path = path
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModel.from_pretrained(model_dir).eval()
        self.lock = threading.Lock()
        self.facts, vecs = [], []
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                if line.strip():
                    row = json.loads(line)
                    self.facts.append(row["text"])
                    vecs.append(row["vec"])
        self.vecs = torch.tensor(vecs) if vecs else torch.zeros(0, 384)
        self.bg = self.embed(BACKGROUND, "passage")

    def embed(self, texts, kind):
        b = self.tok([f"{kind}: {t}" for t in texts], padding=True, truncation=True, max_length=128, return_tensors="pt")
        with torch.inference_mode():
            h = self.model(**b).last_hidden_state
        v = (h * b["attention_mask"][..., None]).sum(1) / b["attention_mask"].sum(1, keepdim=True)
        return torch.nn.functional.normalize(v, dim=-1)

    def recall(self, text, k=3):
        """The stored facts this cue brings up (best first), or []."""
        with self.lock:
            if not self.facts:
                return []
            q = self.embed([text], "query")[0]
            margin = self.vecs @ q - (self.bg @ q).max()
            order = margin.argsort(descending=True)[:k]
            return [self.facts[i] for i in order.tolist() if margin[i] >= MARGIN]

    def add(self, facts):
        """Store new facts (repeats of stored ones are skipped); returns those actually added."""
        facts = [f.strip(" -•*\t.") for f in facts if f.strip(" -•*\t.")]
        if not facts:
            return []
        with self.lock:
            v = self.embed(facts, "passage")
            added = []
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                for text, vec in zip(facts, v):
                    if len(self.facts) and float((self.vecs @ vec).max()) >= SAME:
                        continue
                    self.facts.append(text)
                    self.vecs = torch.cat([self.vecs, vec[None]])
                    f.write(json.dumps({"text": text, "vec": [round(x, 5) for x in vec.tolist()],
                                        "at": time.strftime("%Y-%m-%d %H:%M")}, ensure_ascii=False) + "\n")
                    added.append(text)
            return added


def parse_facts(answer):
    """The extraction answer -> list of facts ("НЕТ" -> [])."""
    answer = (answer or "").strip()
    if not answer or answer.upper().startswith("НЕТ"):
        return []
    # a fact is words: a bare number ("135" - the answer to a sum, 28.10) is not a fact about the person
    return [line for line in answer.splitlines() if line.strip() and "НЕТ" != line.strip().upper()
            and sum(ch.isalpha() for ch in line) >= 4]
