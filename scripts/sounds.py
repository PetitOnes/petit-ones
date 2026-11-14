#!/usr/bin/env python3
"""音のライブラリ: 家に置いた音(WAV)の一覧・取り込み・削除。

ぷちの体は、SD カードの音を鳴らせる(一覧を返す・鳴らす・受け取る)。けれど体から音を取り出すことは
できないので、元になる音は家に置く。置き場所は PETIT_DATA_DIR/sounds/。
ダッシュボードの「音」のページ(/sounds)が、ここから体へ送る。

- 取り込むときに、体が鳴らせる形(モノラル・16 kHz・16 bit の WAV)へ変換する(ffmpeg)
- 名前は、体のファイル名になる。英小文字・数字・_ と - だけ、MAX_NAME 文字まで、末尾は .wav
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import wave
from pathlib import Path

MAX_NAME = 40           # .wav を除いた長さ
MAX_SECONDS = 20.0      # これより長い音は取り込まない(体の SD とメモリのため)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,%d}\.wav$" % (MAX_NAME - 1))


class SoundError(ValueError):
    """取り込めない音・使えない名前。メッセージは人に見せてよい文"""


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def library_dir(base: Path) -> Path:
    return base / "sounds"


def safe_name(raw: str) -> str:
    """人が入れた名前(または元のファイル名)を、体のファイル名にする。使えなければ SoundError"""
    stem = Path(str(raw or "").strip()).name
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", stem).lower()
    stem = re.sub(r"[\s.]+", "_", stem)
    stem = re.sub(r"[^a-z0-9_-]", "", stem).strip("_-")[:MAX_NAME].strip("_-")
    if not stem:
        raise SoundError("名前は、英小文字・数字・_ と - で付けてください(たとえば shizuku)")
    return f"{stem}.wav"


def is_name(name: str) -> bool:
    return bool(_NAME.match(name or ""))


def seconds_of(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return round(w.getnframes() / float(w.getframerate() or 1), 2)
    except (wave.Error, OSError, EOFError):
        return 0.0


def convert(raw: bytes, suffix: str = "") -> bytes:
    """どんな音声でも、体が鳴らせる WAV(モノラル・16 kHz・16 bit)にして返す"""
    if not raw:
        raise SoundError("ファイルが空です")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise SoundError("ファイルが大きすぎます(20 MB まで)")
    with tempfile.TemporaryDirectory() as tmp:
        ext = suffix if re.match(r"^\.[A-Za-z0-9]{1,5}$", suffix or "") else ""
        src = Path(tmp) / f"in{ext}"
        out = Path(tmp) / "out.wav"
        src.write_bytes(raw)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn",
                 "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(out)],
                capture_output=True, check=True, timeout=60,
            )
        except FileNotFoundError as e:
            raise SoundError("この PC に ffmpeg が無いので、変換できません") from e
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise SoundError("音として読めませんでした(WAV・MP3・M4A などを入れてください)") from e
        length = seconds_of(out)
        if length <= 0:
            raise SoundError("音として読めませんでした")
        if length > MAX_SECONDS:
            raise SoundError(f"長すぎます({length:.0f} 秒)。{MAX_SECONDS:.0f} 秒までにしてください")
        return out.read_bytes()


def list_library(base: Path) -> list[dict]:
    """家に置いた音の一覧(名前の順)"""
    out = []
    try:
        files = sorted(library_dir(base).iterdir())
    except OSError:
        return []
    for f in files:
        if f.is_file() and is_name(f.name):
            out.append({"name": f.name, "bytes": f.stat().st_size, "seconds": seconds_of(f)})
    return out


def path_of(base: Path, name: str) -> Path | None:
    """ライブラリにあるその名前のファイル。無い・名前がおかしいなら None"""
    if not is_name(name):
        return None
    p = library_dir(base) / name
    return p if p.is_file() else None


def save(base: Path, name: str, raw: bytes, suffix: str = "", overwrite: bool = False) -> dict:
    """音を変換してライブラリに置く。同じ名前があれば、overwrite でなければ SoundError"""
    fname = safe_name(name)
    target = library_dir(base) / fname
    if target.exists() and not overwrite:
        raise SoundError(f"{fname} はもうあります。別の名前にするか、先に消してください")
    data = convert(raw, suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".wav.tmp")
    tmp.write_bytes(data)
    tmp.replace(target)
    return {"name": fname, "bytes": len(data), "seconds": seconds_of(target)}


def delete(base: Path, name: str) -> bool:
    p = path_of(base, name)
    if p is None:
        return False
    p.unlink()
    return True
