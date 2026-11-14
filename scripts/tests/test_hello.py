"""「ここにいるよ」(scripts/hello.py)のテスト"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hello


def paths(steps):
    return [p for _, p, _ in steps]


def test_fade_in_and_back():
    steps = hello.plan({"color": "#F58E7D", "back_to": "#00afcc"}, False, [], 50, 100)
    colors = [a["color"] for _, p, a in steps if p == "/set_color"]
    assert len(colors) == hello.FADE_STEPS * 2
    assert colors[hello.FADE_STEPS - 1] == "f58e7d"   # 染まりきる
    assert colors[-1] == "00afcc"                      # 元の色に戻る
    assert [t for t, _, _ in steps] == sorted(t for t, _, _ in steps)


def test_color_without_back_stays():
    steps = hello.plan({"color": "#cab8d9", "blink": True}, False, [], 50, 100)
    assert paths(steps) == ["/set_color", "/blink"]


def test_bright_returns_to_what_it_was():
    steps = hello.plan({"bright": True}, False, [], 49, 100)
    assert [(p, a["value"]) for _, p, a in steps] == [("/setbrightness", 100), ("/setbrightness", 49)]
    # いまの明るさが読めなかったら、戻せないので頼まない
    assert hello.plan({"bright": True}, False, [], None, 100) == []


def test_sound_is_quiet_once_and_volume_is_restored():
    steps = hello.plan({"sound": "shining.wav", "volume": 20}, False, ["shining.wav"], 50, 100)
    assert [(p, a.get("value", a.get("name"))) for _, p, a in steps] == [
        ("/setvolume", 20), ("/se_play", "shining.wav"), ("/setvolume", 100)]


def test_no_sound_at_night_or_when_the_body_does_not_have_it():
    spec = {"sound": "shizuku.wav", "volume": 20, "blink": True}
    assert paths(hello.plan(spec, True, ["shizuku.wav"], 50, 100)) == ["/blink"]      # 夜
    assert paths(hello.plan(spec, False, ["pon.wav"], 50, 100)) == ["/blink"]         # 体にその音が無い
    assert paths(hello.plan(spec, False, ["shizuku.wav"], 50, None)) == ["/blink"]    # 音量が読めない


def test_is_night():
    cfg = {"night": [22, 7]}
    assert hello.is_night(cfg, datetime(2026, 11, 14, 23, 0))
    assert hello.is_night(cfg, datetime(2026, 11, 14, 6, 59))
    assert not hello.is_night(cfg, datetime(2026, 11, 14, 14, 0))
    assert hello.is_night({}, datetime(2026, 11, 14, 22, 0))


def test_empty_spec_asks_nothing():
    assert hello.plan({}, False, ["pon.wav"], 50, 100) == []
    assert hello.load_config(Path("/nonexistent")) == {}


def test_blink_comes_before_the_sound():
    """体は音を鳴らし終わるまで待たせるので、まばたきは音より先に頼む"""
    steps = hello.plan({"sound": "pon.wav", "blink": True}, False, ["pon.wav"], 50, 100)
    assert paths(steps) == ["/blink", "/setvolume", "/se_play", "/setvolume"]
