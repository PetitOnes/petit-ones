"""動画メモ(scripts/video_memo.py)のテスト"""

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import video_memo as vm  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg が無い")
NOW = datetime(2026, 11, 14, 22, 40, 5)


def _clip(tmp_path, seconds, size="1280x720") -> bytes:
    """試しの動画(色の縞 + 音)"""
    out = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size={size}:rate=30",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-pix_fmt", "yuv420p", "-shortest", str(out)], check=True)
    return out.read_bytes()


def _size(path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    w, h = out.split(",")[:2]
    return int(w), int(h)


@needs_ffmpeg
def test_save_cuts_and_shrinks(tmp_path):
    row = vm.save(tmp_path, "ari", _clip(tmp_path, 14), ".mp4", "  ねこが  きた  ", NOW)
    assert row["id"] == "20261114_224005" and row["user"] == "ari" and row["title"] == "ねこが きた"
    assert 9.5 <= row["seconds"] <= 10.5                       # 14 秒撮っても、はじめの 10 秒だけ
    video = vm.path_of(tmp_path, "ari", row["id"])
    assert _size(video) == (480, 270) and row["bytes"] < 1_500_000
    assert vm.path_of(tmp_path, "ari", row["id"], "jpg").stat().st_size > 0
    # たて長の動画は、たてが 480
    tall = vm.save(tmp_path, "ari", _clip(tmp_path, 2, "720x1280"), ".mp4", "", NOW)
    assert tall["id"] == "20261114_224005_2" and _size(vm.path_of(tmp_path, "ari", tall["id"])) == (270, 480) and tall["title"] == ""
    vm.save(tmp_path, "kaze", _clip(tmp_path, 1, "320x240"), ".mp4", "", datetime(2026, 11, 14, 23, 0, 0))
    assert [(r["user"], r["id"]) for r in vm.list_all(tmp_path)] == [("kaze", "20261114_230000"), ("ari", "20261114_224005_2"), ("ari", "20261114_224005")]
    assert vm.delete(tmp_path, "ari", row["id"]) is True and vm.delete(tmp_path, "ari", row["id"]) is False
    assert vm.path_of(tmp_path, "ari", row["id"], "jpg") is None and len(vm.list_all(tmp_path)) == 2


@needs_ffmpeg
def test_rejects_what_is_not_video(tmp_path):
    for raw in (b"", b"this is not a video"):
        with pytest.raises(vm.VideoError):
            vm.save(tmp_path, "ari", raw, ".mp4", "", NOW)
    assert vm.list_all(tmp_path) == []
    with pytest.raises(vm.VideoError):
        vm.save(tmp_path, "../x", b"a", ".mp4", "", NOW)


def test_names():
    assert vm.is_id("20261114_224005") and vm.is_id("20261114_224005_2")
    assert not vm.is_id("../x") and not vm.is_id("20261114") and not vm.is_id("")
    assert vm.path_of(Path("/nowhere"), "ari", "../../etc/passwd") is None and vm.path_of(Path("/nowhere"), "a/b", "20261114_224005") is None
    assert vm.clean_title("あ" * 40) == "あ" * 30
