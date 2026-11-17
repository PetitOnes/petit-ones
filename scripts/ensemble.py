#!/usr/bin/env python3
"""合奏: 作った音(と家の音)を、はじまりをずらして重ね、1 つの音にまとめる(2026-11-17、ありさん)。

- 並べるのは: ぷちと家の人が作った音(sounds/made/<だれ>/<名前>.wav)、家の音のライブラリ(by "lib")、
  人のボイスメモ(はなうたなど。kind "memo"、voice_memo/<人>/<ファイル名>。ありさんの頼み)
- 1 本ごとに、はじまり(秒)と大きさ(0〜1)。全体は 30 秒まで。割れないように、まとめたあと大きさをそろえる
- まとめた音は、まとめた人の「作った音」に置く(sing.py と同じ置き場。体へ送る・ぷちに渡すも同じ)
- 自分の音が合奏に入った子には、次の自律行動か会話の頭に 1 行(だれの音が何秒から重なったか)。聞くかはその子が決める
- 鳴らすのは、まずスマホ・PC(ダッシュボード)と、まとめた音を体へ送るところまで。3 人の体で同時に鳴らすのは、あとで試す

Usage:
    python3 ensemble.py notice --character <id> [--mark]   # 自分の音が合奏に入ったこと(まだ伝えていない分)
"""

from __future__ import annotations

import argparse
import re
import sys
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sing  # noqa: E402

MAX_TRACKS = 8
MEMO_EXTS = {".webm", ".wav", ".ogg", ".mp4", ".m4a"}
MAX_SECONDS = 30.0
SR = sing.SR


class EnsembleError(ValueError):
    pass


def _source(base: Path, by: str, name: str, kind: str = "made") -> Path:
    """音の場所。kind が memo ならボイスメモ、by が "lib" なら家の音のライブラリ、ほかは作った音"""
    if kind == "memo":
        d = base / "voice_memo" / by
        p = d / name
        if "/" in name or name.startswith(".") or p.suffix.lower() not in MEMO_EXTS or not p.is_file():
            raise EnsembleError(f"{by} のボイスメモに「{name}」はありません")
        return p
    if by == "lib":
        import sounds
        p = sounds.sound_file(base, name)
        if p is None:
            raise EnsembleError(f"家の音に「{name}」はありません")
        return p
    p = sing.path_of(base, by, name)
    if p is None:
        raise EnsembleError(f"{by} の作った音に「{name}」はありません")
    return p


def _read(path: Path) -> np.ndarray:
    if path.suffix.lower() != ".wav":   # ボイスメモ(webm・m4a など)は ffmpeg でモノラルの wav に
        import subprocess
        try:
            r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-t", str(MAX_SECONDS), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                               capture_output=True, timeout=60, check=True)
        except (OSError, subprocess.SubprocessError) as e:
            raise EnsembleError(f"{path.name} は読めませんでした") from e
        return np.frombuffer(r.stdout, dtype="<i2").astype(np.float64) / 32768.0
    import sound_shape
    try:
        x, sr = sound_shape.read_wav(path)
    except (ValueError, OSError, EOFError, wave.Error) as e:
        raise EnsembleError(f"{path.name} は読めませんでした") from e
    if sr != SR and len(x):
        n = int(round(len(x) * SR / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    return x


def check(tracks: list[dict]) -> list[dict]:
    """並べ方を確かめて、残す形に(by, name, start, vol)"""
    if not isinstance(tracks, list) or not tracks:
        raise EnsembleError("音を 1 つ以上並べてください")
    if len(tracks) > MAX_TRACKS:
        raise EnsembleError(f"並べられるのは {MAX_TRACKS} 本まで")
    out = []
    for t in tracks:
        if not isinstance(t, dict):
            raise EnsembleError("並べ方の形がおかしい")
        by, name, kind = str(t.get("by", "")), str(t.get("name", "")), str(t.get("kind") or "made")
        ok_name = re.fullmatch(r"[^/\\.][^/\\]{0,120}", name) if kind == "memo" else re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,60}", name)
        if kind not in ("made", "memo") or not re.fullmatch(r"[a-zA-Z0-9_]{1,40}", by) or not ok_name:
            raise EnsembleError("音の名前が読めません")
        try:
            start = float(t.get("start", 0) or 0)
            vol = float(t.get("vol", 1) if t.get("vol") is not None else 1)
        except (TypeError, ValueError):
            raise EnsembleError("はじまりと大きさは数字で") from None
        if not (0 <= start <= MAX_SECONDS) or not (0 <= vol <= 1):
            raise EnsembleError(f"はじまりは 0〜{MAX_SECONDS:g} 秒、大きさは 0〜1 で")
        out.append({"by": by, "name": name, "start": round(start, 2), "vol": round(vol, 2)} | ({"kind": "memo"} if kind == "memo" else {}))
    return out


def mix(base: Path, tracks: list[dict]) -> np.ndarray:
    """重ねて 1 つに(-1〜1)。全体の長さは MAX_SECONDS まで"""
    tracks = check(tracks)
    parts = [(int(t["start"] * SR), _read(_source(base, t["by"], t["name"], t.get("kind", "made"))) * t["vol"]) for t in tracks]
    n = min(int(MAX_SECONDS * SR), max(s + len(x) for s, x in parts))
    out = np.zeros(n)
    for s, x in parts:
        if s < n:
            seg = x[: n - s]
            out[s:s + len(seg)] += seg
    peak = float(np.abs(out).max()) if len(out) else 0.0
    if peak > sing.PEAK:
        out *= sing.PEAK / peak
    return out


def wav_bytes(x: np.ndarray) -> bytes:
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def save(base: Path, owner: str, name: str, tracks: list[dict], why: str = "", now: datetime | None = None) -> dict:
    """まとめて、owner の作った音として置く。同じ名前は作り直し(感想は残る)"""
    sing._check(owner, name)
    tracks = check(tracks)
    d = sing.made_dir(base, owner)
    if not (d / f"{name}.wav").exists() and len(list(d.glob("*.wav"))) >= sing.MAX_MADE:
        raise EnsembleError(f"置いておけるのは {sing.MAX_MADE} 個までです。いらない音を消してから")
    x = mix(base, tracks)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{name}.wav.tmp"
    tmp.write_bytes(wav_bytes(x))
    tmp.replace(d / f"{name}.wav")
    old = sing.info_of(base, owner, name) or {}
    info = {"name": name, "by": owner, "at": (now or datetime.now()).isoformat(timespec="minutes"),
            "seconds": round(len(x) / SR, 2), "ensemble": tracks, "why": sing._note(why) or old.get("why", ""),
            "when": old.get("when", ""), "comments": old.get("comments", []) if isinstance(old.get("comments"), list) else [],
            "told": [c for c in old.get("told", []) if isinstance(c, str)] if old.get("ensemble") == tracks else []}
    sing._save_info(base, info)
    return info


def describe(info: dict) -> str:
    """「0 秒 puchiru の ichiteki → 1.5 秒 puchiteya の hikari-agaru」"""
    rows = sorted(info.get("ensemble") or [], key=lambda t: t.get("start", 0))
    def who(t: dict) -> str:
        return "家の音" if t["by"] == "lib" else f"{t['by']} のボイスメモ" if t.get("kind") == "memo" else t["by"]
    return " → ".join(f"{t['start']:g} 秒 {who(t)} の {t['name']}"
                      + (f"(大きさ {t['vol']:g})" if t.get("vol", 1) != 1 else "") for t in rows)


def notice(base: Path, character_id: str, mark: bool = False) -> list[str]:
    """自分の音が入った合奏(まとめた人が自分以外で、まだ伝えていない分)"""
    out = []
    me = Path(sing.__file__).resolve()
    for info in sing.made(base):
        if not info.get("ensemble") or info.get("by") == character_id or character_id in info.get("told", []):
            continue
        mine = [t["name"] for t in info["ensemble"] if t.get("by") == character_id and t.get("kind") != "memo"]
        if not mine:
            continue
        out.append(f"({info['by']} が、あなたの音「{'」「'.join(dict.fromkeys(mine))}」を合奏に入れた: 「{info['name']}」{info.get('seconds', '')} 秒。"
                   f"{describe(info)}。数字と線は python3 {me} look {character_id} {info['name']} --by {info['by']}、"
                   f"鳴らすのは play {character_id} {info['name']} --by {info['by']}。聞いても聞かなくてもいい)")
        if mark:
            info["told"] = list(info.get("told", [])) + [character_id]
            sing._save_info(base, info)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="合奏")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("notice")
    p.add_argument("--character", required=True)
    p.add_argument("--mark", action="store_true")
    a = ap.parse_args(argv)
    for ln in notice(sing.data_dir(), a.character, a.mark):
        print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
