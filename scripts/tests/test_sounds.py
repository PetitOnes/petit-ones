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


# ---- 音ライブラリ: 題と説明、ぷちのお願いと外す(2026-11-16) ----

def _put(base: Path, name: str, seconds: float = 0.5) -> None:
    d = sounds.library_dir(base)
    d.mkdir(parents=True, exist_ok=True)
    tone(d / name, seconds=seconds, rate=16000, channels=1)


def test_meta_shows_in_library(tmp_path):
    _put(tmp_path, "shizuku.wav")
    sounds.set_meta(tmp_path, "shizuku.wav", "しずく", "水が  一滴\nおちる音", by="arisan")
    it = sounds.list_library(tmp_path)[0]
    assert it["title"] == "しずく" and it["description"] == "水が 一滴 おちる音"
    # library.json は音の一覧に混ざらない
    assert [x["name"] for x in sounds.list_library(tmp_path)] == ["shizuku.wav"]


def test_want_resolve_and_notice(tmp_path):
    _put(tmp_path, "shizuku.wav")
    sounds.set_meta(tmp_path, "shizuku.wav", "しずく")
    r = sounds.want(tmp_path, "puchiru", "shizuku", "水の子だから")
    assert r["state"] == "pending" and r["name"] == "shizuku.wav"
    assert sounds.want(tmp_path, "puchiru", "shizuku.wav")["id"] == r["id"]   # 同じお願いは重ねない
    assert "お願い中" in sounds.list_for(tmp_path, "puchiru")[0]
    assert sounds.notice(tmp_path, "puchiru") == []   # まだ答えていない
    sounds.resolve(tmp_path, r["id"], "done", by="arisan")
    assert sounds.requests(tmp_path) == []
    assert "体にある" in sounds.list_for(tmp_path, "puchiru")[0]
    line = sounds.notice(tmp_path, "puchiru", mark=True)
    assert len(line) == 1 and "しずく" in line[0] and "入れてくれた" in line[0]
    assert sounds.notice(tmp_path, "puchiru") == []   # 伝えるのは 1 回
    with pytest.raises(sounds.SoundError):
        sounds.want(tmp_path, "puchiru", "shizuku")   # もう体にある


def test_want_unknown_and_decline(tmp_path):
    with pytest.raises(sounds.SoundError):
        sounds.want(tmp_path, "puchiko", "nai")
    _put(tmp_path, "bell.wav")
    r = sounds.want(tmp_path, "puchiko", "bell")
    sounds.resolve(tmp_path, r["id"], "declined", by="arisan", note="夜はひびくから")
    assert "見送り" in sounds.notice(tmp_path, "puchiko")[0]


def test_sent_fulfils_request(tmp_path):
    _put(tmp_path, "bell.wav")
    sounds.want(tmp_path, "puchiteya", "bell")
    sounds.sent(tmp_path, "puchiteya", "bell.wav", by="arisan")
    assert sounds.requests(tmp_path) == []
    assert "bell.wav" in sounds.on_body_of(tmp_path, "puchiteya")


def test_drop_is_a_request(tmp_path):
    _put(tmp_path, "bell.wav")
    sounds.remember_body(tmp_path, "puchiko", ["bell.wav", "old.wav"])
    with pytest.raises(sounds.SoundError):
        sounds.want(tmp_path, "puchiko", "bell")  # もう体にある(外していない)
    with pytest.raises(sounds.SoundError):
        sounds.drop(tmp_path, "puchiko", "nothing")   # 体に無い音は外せない
    r = sounds.drop(tmp_path, "puchiko", "old", "もう鳴らさない")   # 体にだけある音も外してほしいと言える
    assert r["kind"] == "remove" and sounds.removed_of(tmp_path, "puchiko") == []   # まだ外れていない(お願い)
    assert any("体にだけある音" in x for x in sounds.list_for(tmp_path, "puchiko"))
    sounds.resolve(tmp_path, r["id"], "done", by="arisan")
    assert sounds.removed_of(tmp_path, "puchiko") == ["old.wav"]
    assert "外してくれた" in sounds.notice(tmp_path, "puchiko", mark=True)[0]
    with pytest.raises(sounds.SoundError):
        sounds.drop(tmp_path, "puchiko", "old")   # もう外してある
    sounds.undrop(tmp_path, "puchiko", "old.wav")
    assert sounds.removed_of(tmp_path, "puchiko") == []


def test_opposite_request_withdraws(tmp_path):
    _put(tmp_path, "bell.wav")
    sounds.remember_body(tmp_path, "puchiko", ["bell.wav"])
    sounds.drop(tmp_path, "puchiko", "bell")
    sounds.resolve(tmp_path, sounds.requests(tmp_path)[0]["id"], "done")
    sounds.want(tmp_path, "puchiko", "bell")   # 外した音は、またお願いできる
    assert [r["kind"] for r in sounds.requests(tmp_path)] == ["add"]
    sounds.sent(tmp_path, "puchiko", "bell.wav")
    assert sounds.removed_of(tmp_path, "puchiko") == []   # 入れ直したら外した印は取れる


def test_wish(tmp_path):
    with pytest.raises(sounds.SoundError):
        sounds.wish(tmp_path, "puchiru", "  ")
    r = sounds.wish(tmp_path, "puchiru", "川の せせらぎ")
    assert sounds.wish(tmp_path, "puchiru", "川の せせらぎ")["id"] == r["id"]
    assert any("こういう音がほしい" in x for x in sounds.list_for(tmp_path, "puchiru"))
    _put(tmp_path, "river.wav")
    sounds.set_meta(tmp_path, "river.wav", "かわ")
    sounds.resolve(tmp_path, r["id"], "done", by="arisan", name="river.wav")
    assert "river.wav" in sounds.on_body_of(tmp_path, "puchiru")
    line = sounds.notice(tmp_path, "puchiru")[0]
    assert "せせらぎ" in line and "かわ" in line


def test_delete_clears_meta_and_requests(tmp_path):
    _put(tmp_path, "bell.wav")
    sounds.set_meta(tmp_path, "bell.wav", "鐘")
    sounds.want(tmp_path, "puchiru", "bell")
    assert sounds.delete(tmp_path, "bell.wav")
    assert sounds.load_meta(tmp_path) == {} and sounds.requests(tmp_path) == []
