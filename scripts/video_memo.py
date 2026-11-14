#!/usr/bin/env python3
"""動画メモ: 人が撮る、短い動画のメモ(MAX_SECONDS 秒まで。画質を落として小さく残す)。

撮れるのは人だけ(ダッシュボードの「動画メモ」)。家の人どうしで見られる。ぷちには渡していない
(ぷちの見方は、ぷちたちと相談して決める。2026-11-14 ありさん)。

置き場所は PETIT_DATA_DIR/video_memo/<ユーザー名>/:

    20261114_223700.mp4    # 本体(H.264 + AAC、長いほうの辺 LONG_SIDE まで、MAX_SECONDS 秒で切る)
    20261114_223700.jpg    # 一覧に出す 1 枚
    .meta.json             # {"20261114_223700": {"title": "ひとこと"}}

- 取り込むとき、どんな動画でも上の形に変換する(ffmpeg)。長く撮っても、はじめの MAX_SECONDS 秒だけ残る
- 名前は撮った時刻。同じ秒に 2 本あれば _2 を付ける
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

MAX_SECONDS = 10
LONG_SIDE = 480                       # 長いほうの辺(px)
MAX_UPLOAD_BYTES = 300 * 1024 * 1024  # スマホの元の動画は大きい(変換して 1MB 前後になる)
TITLE_MAX = 30
_ID = re.compile(r"^\d{8}_\d{6}(_\d+)?$")
_USER = re.compile(r"^[a-zA-Z0-9_]+$")


class VideoError(ValueError):
    """取り込めない動画・使えない名前。メッセージは人に見せてよい文"""


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def user_dir(base: Path, user: str) -> Path:
    if not _USER.match(user or ""):
        raise VideoError("名前がおかしい")
    return base / "video_memo" / user


def is_id(memo_id: str) -> bool:
    return bool(_ID.match(memo_id or ""))


def _meta(d: Path) -> dict:
    try:
        raw = json.loads((d / ".meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_meta(d: Path, meta: dict) -> None:
    tmp = d / ".meta.json.tmp"
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(d / ".meta.json")


def _run(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], capture_output=True, check=True, timeout=180)


def seconds_of(path: Path) -> float:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, check=True, timeout=30).stdout.strip()
        return round(float(out), 1)
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0.0


def convert(src: Path, out_video: Path, out_thumb: Path) -> None:
    """どんな動画でも、小さい MP4(はじめの MAX_SECONDS 秒・長いほうの辺 LONG_SIDE まで)と、一覧用の 1 枚にする"""
    fit = f"scale=w={LONG_SIDE}:h={LONG_SIDE}:force_original_aspect_ratio=decrease:force_divisible_by=2"
    try:
        _run(["-i", str(src), "-t", str(MAX_SECONDS), "-vf", f"{fit},fps=24", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
              "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "48k", "-ac", "1", "-movflags", "+faststart", str(out_video)])
        _run(["-i", str(out_video), "-frames:v", "1", "-q:v", "5", str(out_thumb)])
    except FileNotFoundError as e:
        raise VideoError("この PC に ffmpeg が無いので、変換できません") from e
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        raise VideoError("動画として読めませんでした") from e
    if seconds_of(out_video) <= 0:
        raise VideoError("動画として読めませんでした")


def clean_title(title: str) -> str:
    return " ".join(str(title or "").split())[:TITLE_MAX]


def save(base: Path, user: str, raw: bytes, suffix: str = "", title: str = "", now: datetime | None = None) -> dict:
    """動画を変換して、その人のメモに置く"""
    if not raw:
        raise VideoError("ファイルが空です")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise VideoError(f"ファイルが大きすぎます({MAX_UPLOAD_BYTES // 1024 // 1024} MB まで)")
    d = user_dir(base, user)
    d.mkdir(parents=True, exist_ok=True)
    stem = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    memo_id = next(i for i in [stem, *(f"{stem}_{n}" for n in range(2, 100))] if not (d / f"{i}.mp4").exists())
    with tempfile.TemporaryDirectory() as tmp:
        ext = suffix if re.match(r"^\.[A-Za-z0-9]{1,5}$", suffix or "") else ""
        src = Path(tmp) / f"in{ext}"
        src.write_bytes(raw)
        video, thumb = Path(tmp) / "out.mp4", Path(tmp) / "out.jpg"
        convert(src, video, thumb)
        (d / f"{memo_id}.mp4.tmp").write_bytes(video.read_bytes())
        (d / f"{memo_id}.mp4.tmp").replace(d / f"{memo_id}.mp4")
        (d / f"{memo_id}.jpg").write_bytes(thumb.read_bytes())
    title = clean_title(title)
    if title:
        meta = _meta(d)
        meta[memo_id] = {"title": title}
        _save_meta(d, meta)
    return _row(d, user, memo_id, _meta(d))


def _row(d: Path, user: str, memo_id: str, meta: dict) -> dict:
    f = d / f"{memo_id}.mp4"
    info = meta.get(memo_id) if isinstance(meta.get(memo_id), dict) else {}
    ts = datetime.strptime(memo_id[:15], "%Y%m%d_%H%M%S")
    return {"id": memo_id, "user": user, "ts": ts.isoformat(), "title": str(info.get("title") or ""),
            "seconds": seconds_of(f), "bytes": f.stat().st_size}


def list_all(base: Path) -> list[dict]:
    """みんなの動画メモ(新しい順)"""
    out = []
    root = base / "video_memo"
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        if not d.is_dir() or not _USER.match(d.name):
            continue
        meta = _meta(d)
        for f in d.glob("*.mp4"):
            if is_id(f.stem):
                out.append(_row(d, d.name, f.stem, meta))
    return sorted(out, key=lambda r: (r["ts"], r["id"]), reverse=True)


def path_of(base: Path, user: str, memo_id: str, kind: str = "mp4") -> Path | None:
    """その動画メモの本体(mp4)か 1 枚(jpg)。無い・名前がおかしいなら None"""
    if not is_id(memo_id) or kind not in ("mp4", "jpg") or not _USER.match(user or ""):
        return None
    p = base / "video_memo" / user / f"{memo_id}.{kind}"
    return p if p.is_file() else None


def delete(base: Path, user: str, memo_id: str) -> bool:
    p = path_of(base, user, memo_id)
    if p is None:
        return False
    p.unlink()
    p.with_suffix(".jpg").unlink(missing_ok=True)
    meta = _meta(p.parent)
    if meta.pop(memo_id, None) is not None:
        _save_meta(p.parent, meta)
    return True
