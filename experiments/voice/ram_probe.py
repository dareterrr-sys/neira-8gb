"""Where the voice's RAM goes (28.10): private bytes of this process after each loading step, as the server does them."""
import json
import os

import psutil
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "voice_config.json"), encoding="utf-8"))
me = psutil.Process()


def ram(tag):
    print(f"{tag:34s} private {me.memory_info().private / 2 ** 30:5.1f} GB", flush=True)


ram("python")
torch.zeros(1, device="cuda")
ram("torch + CUDA context")
from faster_qwen3_tts import FasterQwen3TTS  # noqa: E402
model = FasterQwen3TTS.from_pretrained(CFG["model"], max_seq_len=2048)
ram("model loaded (bf16 on GPU)")
import int8_voice  # noqa: E402
int8_voice.shrink(model.model.model, int8=True)
ram("int8 + embedding on CPU")
lv = int8_voice.Int8MergeVoices(model.model.model, CFG["sounds_lora"])
ram("sounds LoRA")
col = int8_voice.Int8MergeVoices(model.model.model, CFG["colleague_lora"])
ram("colleague LoRA")
model.generate_custom_voice(text="Проверка связи.", speaker=CFG["speaker"], language=CFG["language"])
ram("first sentence (graphs)")
from park import Parking  # noqa: E402
p = Parking(model)
p.park()
ram("parked")
p.unpark()
ram("unparked")
