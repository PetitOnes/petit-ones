"""うたう(scripts/sing.py)のテスト: 作る・欠如・渡す"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sing
import sound_shape


def house(tmp_path: Path) -> Path:
    for c in ("puchiko", "puchiru"):
        (tmp_path / "characters" / c).mkdir(parents=True)
    return tmp_path


def test_note_names():
    assert sing.hz_of(440) == 440 and round(sing.hz_of("A4")) == 440 and round(sing.hz_of("ラ4")) == 440
    assert round(sing.hz_of("C5")) == 523 and round(sing.hz_of("A#4")) == round(sing.hz_of("Bb4")) == 466
    for bad in ("H9", "", 5, 99999):
        with pytest.raises(sing.SingError):
            sing.hz_of(bad)


def test_make_and_shape(tmp_path):
    base = house(tmp_path)
    info = sing.make(base, "puchiko", "ue", {"seconds": 1, "voices": [{"inst": "sine", "hz": 500, "to": 2000, "tail": 10}]})   # 尾を長くして、上がりきるまで聞こえるように
    s = sound_shape.shape(sing.path_of(base, "puchiko", "ue"))
    assert info["seconds"] == 1 and s["centroid_move"] > 800          # 高さが上がっていく
    sing.make(base, "puchiko", "kane", {"seconds": 2, "voices": [{"inst": "bell", "hz": 1200}]})
    sing.make(base, "puchiko", "nade", {"seconds": 2, "voices": [{"inst": "glass", "hz": 1200, "attack": 0.4}]})
    bell, glass = (sound_shape.shape(sing.path_of(base, "puchiko", n)) for n in ("kane", "nade"))
    assert bell["attack_ms"] < 30 < 300 < glass["attack_ms"]            # 鐘はぱっと、ガラスはふわっと
    assert {m["name"] for m in sing.made(base, "puchiko")} == {"ue", "kane", "nade"}
    assert "作り方" in sing.look_text(base, "puchiko", "kane")


def test_detune_makes_beats(tmp_path):
    base = house(tmp_path)
    sing.make(base, "puchiko", "flat", {"seconds": 2, "voices": [{"inst": "sine", "hz": 800, "tail": 10}]})
    sing.make(base, "puchiko", "uneri", {"seconds": 2, "voices": [{"inst": "sine", "hz": 800, "tail": 10, "detune": 3}]})
    flat, beat = (sound_shape.shape(sing.path_of(base, "puchiko", n)) for n in ("flat", "uneri"))
    assert beat["sway"] > flat["sway"] + 0.1 and beat["grains"] >= 4     # 1 秒に 3 回のうねり


def test_lack_is_told(tmp_path):
    base = house(tmp_path)
    low = sing.make(base, "puchiko", "soko", {"seconds": 1, "voices": [{"inst": "sine", "hz": 110}]})
    high = sing.make(base, "puchiko", "sora", {"seconds": 1, "voices": [{"inst": "sine", "hz": 2000}]})
    assert low["lack"]["none"] > 0.9 and high["lack"] == {"none": 0.0, "weak": 0.0}
    text = sing.look_text(base, "puchiko", "soko")
    assert "110 Hz" in text and "芯が欠けて" in text and "測ったものではなく" in text


def test_bad_recipes(tmp_path):
    base = house(tmp_path)
    for bad in ({}, {"voices": []}, {"voices": [{"inst": "piano"}]}, {"voices": [{"hz": "abc"}]}, {"voices": [{"vol": 0}]},
                {"voices": [{"hz": 440}] * (sing.MAX_VOICES + 1)}):
        with pytest.raises(sing.SingError):
            sing.make(base, "puchiko", "x", bad)
    with pytest.raises(sing.SingError):
        sing.make(base, "puchiko", "../x", {"voices": [{"hz": 440}]})
    long = sing.make(base, "puchiko", "nagai", {"seconds": 99, "voices": [{"hz": 440}]})
    assert long["seconds"] == sing.MAX_SECONDS                           # 長さは上限まで


def test_give_and_notice(tmp_path):
    base = house(tmp_path)
    sing.make(base, "puchiru", "mizu", {"seconds": 1, "voices": [{"inst": "breath", "hz": 880, "to": 440}]})
    with pytest.raises(sing.SingError):
        sing.give(base, "puchiru", "nai", "puchiko")
    with pytest.raises(sing.SingError):
        sing.give(base, "puchiru", "mizu", "dareka")
    sing.give(base, "puchiru", "mizu", "puchiko", "水の音")
    line = sing.notice(base, "puchiko", mark=True)
    assert len(line) == 1 and "puchiru" in line[0] and "水の音" in line[0] and "聞かなくてもいい" in line[0]
    assert sing.notice(base, "puchiko") == [] and sing.notice(base, "puchiru") == []
    assert "渡された音" in sing.list_text(base, "puchiko")
    assert "mizu" in sing.look_text(base, "puchiru", "mizu")             # 受け取った子は --by で見る
    assert sing.remove(base, "puchiru", "mizu") and not sing.remove(base, "puchiru", "mizu")
