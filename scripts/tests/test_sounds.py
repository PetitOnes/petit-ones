"""音のライブラリ(scripts/sounds.py)のテスト"""

import math
import shutil
import struct
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sounds

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg が無い")


def tone(path: Path, seconds: float = 0.5, rate: int = 44100, channels: int = 2) -> bytes:
    """試しの音(ステレオ・44.1 kHz)を作って、中身を返す"""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) * channels
            for i in range(int(rate * seconds))
        )
        w.writeframes(frames)
    return path.read_bytes()


def test_safe_name():
    assert sounds.safe_name("Shizuku Drop.MP3") == "shizuku_drop.wav"
    assert sounds.safe_name("happy_bell.wav") == "happy_bell.wav"
    assert sounds.safe_name("../../etc/passwd") == "passwd.wav"
    assert sounds.safe_name("a" * 80 + ".wav") == "a" * sounds.MAX_NAME + ".wav"
    for bad in ("", "みずのおと.wav", "...", "___"):
        with pytest.raises(sounds.SoundError):
            sounds.safe_name(bad)


def test_is_name_rejects_paths():
    assert sounds.is_name("pon.wav")
    assert not sounds.is_name("../pon.wav")
    assert not sounds.is_name("pon.mp3")
    assert not sounds.is_name("Pon.wav")


@needs_ffmpeg
def test_save_converts_to_what_the_body_can_play(tmp_path):
    raw = tone(tmp_path / "src.wav")
    item = sounds.save(tmp_path, "My Tone.wav", raw, ".wav")
    assert item["name"] == "my_tone.wav"
    with wave.open(str(tmp_path / "sounds" / "my_tone.wav"), "rb") as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (1, 16000, 2)
    assert 0.4 < item["seconds"] < 0.6
    assert [x["name"] for x in sounds.list_library(tmp_path)] == ["my_tone.wav"]


@needs_ffmpeg
def test_same_name_is_not_overwritten_silently(tmp_path):
    raw = tone(tmp_path / "src.wav")
    sounds.save(tmp_path, "tone", raw, ".wav")
    with pytest.raises(sounds.SoundError):
        sounds.save(tmp_path, "tone", raw, ".wav")
    sounds.save(tmp_path, "tone", raw, ".wav", overwrite=True)


@needs_ffmpeg
def test_too_long_or_not_a_sound_is_refused(tmp_path):
    with pytest.raises(sounds.SoundError):
        sounds.save(tmp_path, "long", tone(tmp_path / "l.wav", seconds=sounds.MAX_SECONDS + 2, rate=8000, channels=1), ".wav")
    with pytest.raises(sounds.SoundError):
        sounds.save(tmp_path, "text", b"this is not a sound", ".wav")
    with pytest.raises(sounds.SoundError):
        sounds.save(tmp_path, "empty", b"", ".wav")
    assert sounds.list_library(tmp_path) == []


@needs_ffmpeg
def test_delete_and_path_of(tmp_path):
    sounds.save(tmp_path, "tone", tone(tmp_path / "src.wav"), ".wav")
    assert sounds.path_of(tmp_path, "tone.wav") is not None
    assert sounds.path_of(tmp_path, "../tone.wav") is None
    assert sounds.delete(tmp_path, "tone.wav") is True
    assert sounds.delete(tmp_path, "tone.wav") is False


def test_list_ignores_other_files(tmp_path):
    (tmp_path / "sounds").mkdir()
    (tmp_path / "sounds" / "memo.txt").write_text("x")
    (tmp_path / "sounds" / "tone.wav.tmp").write_text("x")
    assert sounds.list_library(tmp_path) == []
    assert sounds.list_library(tmp_path / "none") == []
