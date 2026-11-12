import asyncio
import json
from types import SimpleNamespace

from open_llm_vtuber.neira_signals import stats_message, stress_message, send_stats
from open_llm_vtuber.agent.transformers import actions_extractor
from open_llm_vtuber.agent.output_types import Actions
from open_llm_vtuber.live2d_model import Live2dModel


def test_stats_format():
    m = stats_message({"predicted_n": 40, "predicted_per_second": 51.234, "prompt_n": 100, "cache_n": 900})
    assert m == {"type": "neira-stats", "tok_s": 51.23, "tokens": 40, "ctx_tokens": 1040}
    assert stats_message(None) is None and stats_message({"predicted_n": 0}) is None


def test_stress_format():
    assert stress_message(1.7, "x") == {"type": "neira-stress", "level": 1.0, "reason": "x"}
    assert stress_message(0)["level"] == 0.0


def test_send_stats():
    sent = []

    async def ws(t):
        sent.append(json.loads(t))

    llm = SimpleNamespace(last_timings={"predicted_n": 5, "predicted_per_second": 10.0, "prompt_n": 1})
    asyncio.run(send_stats(ws, llm))
    assert sent and sent[0]["type"] == "neira-stats" and sent[0]["tokens"] == 5
    sent.clear()
    asyncio.run(send_stats(ws, SimpleNamespace(last_timings=None)))
    assert not sent


class FakeModel:
    emo_map = {"calm": 0, "surprise": 1, "cute": 2, "sad": 3}
    extract_emotion = Live2dModel.extract_emotion
    remove_emotion_keywords = Live2dModel.remove_emotion_keywords


def _run(texts):
    from open_llm_vtuber.utils.sentence_divider import SentenceWithTags

    async def src():
        for t in texts:
            yield SentenceWithTags(text=t, tags=[])

    @actions_extractor(FakeModel())
    async def f():
        async for x in src():
            yield x

    async def go():
        return [s.text for s, _ in [x async for x in f()]]

    return asyncio.run(go())


def test_stacked_tags_spread_over_sentences():
    out = _run(["[surprise][cute][sad] Раз.", "Два.", "Три.", "Четыре."])
    assert out == ["[surprise] Раз.", "[cute] Два.", "[sad] Три.", "Четыре."]


def test_own_tags_untouched():
    out = _run(["[cute] Раз.", "[sad] Два.", "Три."])
    assert out == ["[cute] Раз.", "[sad] Два.", "Три."]


def test_tags_do_not_leak_between_answers():
    assert _run(["[surprise][cute] Раз."]) == ["[surprise] Раз."]
    assert _run(["Два."]) == ["Два."]


def test_stress_level():
    from open_llm_vtuber.neira_signals import stress_level
    assert stress_level(4000, 40) == (0.0, "")
    assert stress_level(300, 40)[0] == 1.0 and "VRAM" in stress_level(300, 40)[1]
    assert abs(stress_level(650, None)[0] - 0.5) < 1e-9
    assert stress_level(4000, 8)[0] == 1.0 and "скорость" in stress_level(4000, 8)[1]
    assert stress_level(4000, 14)[0] == 0.5
    assert stress_level(None, None, failed=True)[0] == 1.0


def test_stress_monitor_throttle():
    from open_llm_vtuber.neira_signals import StressMonitor
    t = [0.0]
    vram = [4000.0]
    calls = []

    def rv():
        calls.append(1)
        return vram[0]

    mon = StressMonitor(read_vram=rv, clock=lambda: t[0])

    async def go():
        assert await mon.message(40) is None            # calm, same as the start level 0
        vram[0] = 300.0
        t[0] = 1.0
        assert await mon.message(40) is None            # VRAM cached (5 s), still calm
        t[0] = 6.0
        m = await mon.message(40)
        assert m["type"] == "neira-stress" and m["level"] == 1.0
        t[0] = 6.5
        assert await mon.message(40, failed=True) is None   # same level: no resend
        vram[0] = 4000.0
        t[0] = 12.0
        m = await mon.message(40)
        assert m["level"] == 0.0

    asyncio.run(go())
    assert len(calls) == 3
