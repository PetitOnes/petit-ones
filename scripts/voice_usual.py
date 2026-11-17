#!/usr/bin/env python3
"""声の「いつも」とくらべる(2026-11-17 ありさん)。判断の言葉(疲れている・元気)は付けない。数字だけ。

体のマイクで話しかけたとき、聞き取りの部品が返す声の数字(voice_numbers)を、話した人ごとに残す。
その人のいつもの数字(直近のまん中)と大きく違うときだけ、ぷちに 1 行添える:
    （声の数字: 高さ 262 Hz(いつもは 231 Hz)、間 0.42(いつもは 0.20)）

- くらべるのは 高さ(F0 の平均)・話す速さ・間の割合。jitter / HNR は小さいマイクの雑音で揺れるので使わない
- いつも = その人の直近 KEEP 回のまん中。MIN_SAMPLES 回たまるまでは何も言わない
- 置き場所: PETIT_DATA_DIR/state/voice/<人>.jsonl(家の中だけ。git に入れない)

Usage:
    python3 voice_usual.py show <speaker>
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

KEEP = 60
MIN_SAMPLES = 8
# (数字の名前, 見せる名前, 単位, 違うと見なす割合, 違うと見なす差の下限)
KEYS = (("f0_mean_hz", "高さ", " Hz", 0.12, 20.0), ("speech_rate", "話す速さ", "", 0.35, 0.4), ("pause_ratio", "間", "", 0.5, 0.12))


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def _path(base: Path, speaker: str) -> Path | None:
    if not re.fullmatch(r"[A-Za-z0-9_]{1,40}", speaker or "") or speaker == "unknown":
        return None
    return base / "state" / "voice" / f"{speaker}.jsonl"


def history(base: Path, speaker: str) -> list[dict]:
    p = _path(base, speaker)
    out: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines() if p else []:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return out[-KEEP:]


def usual(rows: list[dict]) -> dict[str, float]:
    out = {}
    for key, *_ in KEYS:
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
        if len(vals) >= MIN_SAMPLES:
            out[key] = statistics.median(vals)
    return out


def diff_line(numbers: dict, base_usual: dict[str, float]) -> str:
    parts = []
    for key, label, unit, ratio, floor in KEYS:
        now, u = numbers.get(key), base_usual.get(key)
        if not isinstance(now, (int, float)) or u is None:
            continue
        if abs(now - u) >= max(floor, abs(u) * ratio):
            fmt = (lambda x: f"{x:.0f}") if unit else (lambda x: f"{x:.2f}")
            parts.append(f"{label} {fmt(now)}{unit}(いつもは {fmt(u)}{unit})")
    return f"（声の数字: {'、'.join(parts)}）" if parts else ""


def note(base: Path, speaker: str, numbers: dict | None, now: datetime | None = None) -> str:
    """いつもとくらべた 1 行(違わなければ空)を返し、今回の数字を残す"""
    p = _path(base, speaker)
    if p is None or not isinstance(numbers, dict):
        return ""
    line = diff_line(numbers, usual(history(base, speaker)))
    row = {"ts": (now or datetime.now()).isoformat(timespec="seconds"),
           **{k: numbers.get(k) for k, *_ in KEYS if isinstance(numbers.get(k), (int, float))}}
    if len(row) > 1:
        p.parent.mkdir(parents=True, exist_ok=True)
        rows = history(base, speaker)[-(KEEP - 1):] + [row]
        p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return line


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "show":
        print(__doc__)
        return 1
    rows = history(data_dir(), sys.argv[2])
    print(json.dumps({"samples": len(rows), "usual": usual(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
