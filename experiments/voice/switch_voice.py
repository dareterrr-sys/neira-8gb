"""Switch Neira (Open-LLM-VTuber conf.yaml) between her own voice and the old XTTS voice.

  new: tts_model openai_tts -> this folder's voice server (fine-tuned Qwen3-TTS, http://127.0.0.1:8090/v1);
       whole sentences only (faster_first_response off: cutting the first sentence at a comma spoils intonation)
  old: tts_model coqui_tts (XTTS), faster_first_response on
A copy of the original file is kept as conf.yaml.before-new-voice. Restart Neira afterwards.
Which pair of trained voices the voice server uses (copied into voice_config.json; the earlier one is kept as
voice_config.before-night2.json):
  ru: main voice taught with the Russian language token (refvoice_main_ru_b3) + sounds v16
  v3: the main voice v3 (refvoice_ru3 epoch-3) + sounds v15
  vector: ru + mood tags also move the voice vector (mood_dirs_char2.npz, see MoodVector in the server)
  k2: main voice k2 epoch 5 (only user-confirmed data) moved toward RefVoice (voice_shift x1) + mood vectors,
      no sounds version yet (v20b was trained for b3)
  k4: the same with main voice k4 epoch 3 (Char2 recoloured by the mix RVC: fewest slips)
  k5: the same with main voice k5 epoch 5 (mix recolour + RefVoice's melody: closest manner, few slips)
  k5s: k5 + the sounds version v21b (laughs made the k5 way)
  k7s: main voice k7 (selective stress marks, RUAccent service on :8093) + sounds v23
Usage: python switch_voice.py new|old|ru|vector|k2|k4|k5|k5s|k7s
"""
import os
import re
import shutil
import sys

CONF = r"D:\AI\Open-LLM-VTuber\conf.yaml"
HERE = os.path.dirname(os.path.abspath(__file__))
PAIRS = {"ru": "voice_config.ru.json", "v3": "voice_config.v3.json", "vector": "voice_config.vector.json", "k2": "voice_config.k2.json", "k4": "voice_config.k4.json", "k5": "voice_config.k5.json", "k5s": "voice_config.k5s.json", "k7s": "voice_config.k7s.json"}


def main():
    mode = sys.argv[1]
    if mode in PAIRS:
        shutil.copy(os.path.join(HERE, PAIRS[mode]), os.path.join(HERE, "voice_config.json"))
        print(f"Neira's voice pair: {mode} (restart the voice server / Neira)")
        return
    text = open(CONF, encoding="utf-8").read()
    backup = CONF + ".before-new-voice"
    if not os.path.exists(backup):
        shutil.copy(CONF, backup)
    if mode == "new":
        text = re.sub(r"tts_model: '[a-z_]+'", "tts_model: 'openai_tts'", text, count=1)
        text = re.sub(r"(openai_tts:.*?\n\s+model: )'[^']*'", r"\1'neira'", text, count=1, flags=re.S)
        text = re.sub(r"(openai_tts:.*?\n\s+voice: )'[^']*'", r"\1'refvoice'", text, count=1, flags=re.S)
        text = re.sub(r"(openai_tts:.*?\n\s+base_url: )'[^']*'", r"\1'http://127.0.0.1:8090/v1'", text, count=1, flags=re.S)
        text = re.sub(r"(openai_tts:.*?\n\s+file_extension: )'[^']*'", r"\1'wav'", text, count=1, flags=re.S)
        text = text.replace("faster_first_response: True", "faster_first_response: False", 1)
    else:
        text = re.sub(r"tts_model: '[a-z_]+'", "tts_model: 'coqui_tts'", text, count=1)
        text = text.replace("faster_first_response: False", "faster_first_response: True", 1)
    open(CONF, "w", encoding="utf-8").write(text)
    print(f"Neira voice: {mode}")


if __name__ == "__main__":
    main()
