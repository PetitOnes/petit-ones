"""音のかたち(scripts/sound_shape.py と、sounds.py の look / words)のテスト"""

import math
import struct
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sound_shape
import sounds

RATE = 16000


def write(path: Path, samples: list[float]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, v)) * 32000)) for v in samples))
    return path


def tone(freq: float, seconds: float, decay: float = 0.0) -> list[float]:
    return [math.sin(2 * math.pi * freq * i / RATE) * math.exp(-decay * i / RATE) for i in range(int(RATE * seconds))]


def noise(seconds: float) -> list[float]:
    x, out = 12345, []
    for _ in range(int(RATE * seconds)):
        x = (1103515245 * x + 12345) % (2 ** 31)
        out.append(x / 2 ** 30 - 1)
    return out


def test_pitch_and_roughness(tmp_path):
    low = sound_shape.shape(write(tmp_path / "low.wav", tone(300, 0.5)))
    high = sound_shape.shape(write(tmp_path / "high.wav", tone(3000, 0.5)))
    hiss = sound_shape.shape(write(tmp_path / "hiss.wav", noise(0.5)))
    assert abs(low["centroid"] - 300) < 40 and abs(high["centroid"] - 3000) < 80
    assert low["rough"] < 0.1 < 0.6 < hiss["rough"]          # 澄んだ音は 0 の近く、ノイズは 1 の近く
    assert hiss["spread"] > high["spread"]


def test_attack_tail_and_line(tmp_path):
    hit = sound_shape.shape(write(tmp_path / "hit.wav", tone(800, 1.0, decay=12)))    # 一瞬で立ち上がって、尾を引く
    swell = [v * min(1.0, i / (RATE * 0.5)) for i, v in enumerate(tone(800, 1.0))]     # ふわっと立ち上がる
    slow = sound_shape.shape(write(tmp_path / "swell.wav", swell))
    assert hit["attack_ms"] <= 20 and slow["attack_ms"] >= 300
    assert 0.1 < hit["tail"] < 0.4 and hit["peak_at"] < 0.1
    assert hit["line"][0] == "█" and hit["line"][-1] == "▁" and len(hit["line"]) == 40
    assert hit["grains"] == 1 and hit["overlap"] is None


def test_grains_and_overlap(tmp_path):
    gap = [0.0] * int(RATE * 0.15)
    apart = tone(600, 0.05) + gap + tone(600, 0.05) + gap + tone(600, 0.05)
    s = sound_shape.shape(write(tmp_path / "apart.wav", apart))
    assert s["grains"] == 3 and s["overlap"] < 0.1           # はっきり分かれた 3 つの粒
    joined = [v * (0.6 + 0.4 * math.sin(2 * math.pi * 4 * i / RATE)) for i, v in enumerate(tone(600, 1.0))]
    j = sound_shape.shape(write(tmp_path / "joined.wav", joined))
    assert j["grains"] >= 3 and j["overlap"] > 0.2           # つながった粒


def test_pitch_movement(tmp_path):
    n = int(RATE * 0.6)
    sweep, phase = [], 0.0
    for i in range(n):
        phase += 2 * math.pi * (400 + 2000 * i / n) / RATE
        sweep.append(math.sin(phase))
    s = sound_shape.shape(write(tmp_path / "up.wav", sweep))
    assert s["centroid_move"] > 1000                          # はじめより、おわりのほうが高い


def test_silent_and_text(tmp_path):
    s = sound_shape.shape(write(tmp_path / "none.wav", [0.0] * RATE))
    assert s["silent"] and "音がほとんど" in sound_shape.text("none.wav", s)
    t = sound_shape.text("hit.wav", sound_shape.shape(write(tmp_path / "hit.wav", tone(800, 0.5, decay=10))))
    assert "音量の線" in t and "高さの重心" in t and "8000 Hz より上は入っていません" in t


def test_look_from_library_and_backup(tmp_path):
    write(sounds.library_dir(tmp_path) / "bell.wav", tone(2000, 0.3, decay=8))
    write(tmp_path / "sd_backups" / "b" / "wav" / "pon.wav", tone(500, 0.1, decay=30))
    assert list(sounds.known_sounds(tmp_path)) == ["bell.wav", "pon.wav"]
    a = sounds.shape_of(tmp_path, "bell")
    assert sounds.shape_of(tmp_path, "bell.wav") == a          # 2 回目は覚えている分
    assert "bell" in sound_shape.table({n: sounds.shape_of(tmp_path, n) for n in sounds.known_sounds(tmp_path)})
    assert "重心Hz" in sound_shape.compare("pon.wav", sounds.shape_of(tmp_path, "pon"), "bell.wav", a)
    with pytest.raises(sounds.SoundError):
        sounds.shape_of(tmp_path, "nai")


def test_words_are_kept(tmp_path):
    sounds.add_word(tmp_path, "puchiteya", "shining", "guess", "ゆっくり消える、黄色い音")
    sounds.add_word(tmp_path, "puchiteya", "shining", "heard", "思ったより低かった")
    sounds.add_word(tmp_path, "puchiko", "shining.wav", "tag", "紫ではない")
    assert [w["kind"] for w in sounds.words(tmp_path, "puchiteya", "shining")] == ["guess", "heard"]   # 予想もずれも、消さずに残る
    assert len(sounds.words(tmp_path, name="shining.wav")) == 3
    assert "[予想]" in sounds.words_text(sounds.words(tmp_path))
    with pytest.raises(sounds.SoundError):
        sounds.add_word(tmp_path, "puchiko", "shining", "tag", "  ")
