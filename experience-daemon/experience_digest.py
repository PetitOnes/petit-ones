#!/usr/bin/env python3
"""体験バッファのダイジェスト生成。

カーソル（前回既読位置）以降の未読イベントを日本語の1行ずつに整形して標準出力する。
未読が無ければ何も出力しない（節ごと省略できるように）。

Usage:
    python3 experience_digest.py --character puchiko
    python3 experience_digest.py --character puchiko --mark-read
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))


def _character_dir(character: str) -> Path:
    return DATA_DIR / "characters" / character


def _experience_dir(character: str) -> Path:
    return _character_dir(character) / "state" / "experience"


def _cursor_path(character: str) -> Path:
    return _character_dir(character) / "state" / "experience_cursor"


def _read_cursor(character: str) -> datetime:
    path = _cursor_path(character)
    if not path.exists():
        # カーソル未作成＝初回。datetime.min にしておけば、当日・前日分の
        # ファイルしか読まないので勝手に範囲が絞られる。
        return datetime.min
    try:
        text = path.read_text(encoding="utf-8").strip()
        return datetime.fromisoformat(text)
    except (OSError, ValueError):
        return datetime.min


def _write_cursor(character: str, ts: datetime) -> None:
    path = _cursor_path(character)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ts.isoformat(timespec="seconds"), encoding="utf-8")


def _load_events(character: str, cursor: datetime) -> list[dict]:
    """当日・前日の JSONL だけを読み、cursor より新しいイベントを返す（時刻昇順）。"""
    exp_dir = _experience_dir(character)
    events: list[dict] = []
    today = datetime.now().date()
    for day_offset in (1, 0):  # 前日→当日の順で読む
        day = today - timedelta(days=day_offset)
        path = exp_dir / f"{day.strftime('%Y%m%d')}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                ts = datetime.fromisoformat(record["ts"])
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            if ts > cursor:
                events.append(record)
    events.sort(key=lambda r: r["ts"])
    return events


# 体が起動したわけ(ファームが返す名前)→ ぷちに渡す言い方。分からないときは何も添えない
RESTART_WHY = {
    "poweron": "（電源が入った）",
    "ext": "（リセットされた）",
    "sw": "（書き込みか、命令で）",
    "panic": "（体の不具合で、ひとりでに）",
    "wdt": "（体が固まって、ひとりでに）",
    "brownout": "（電圧が下がって、ひとりでに）",
}


def _format_duration_sec(sec: float) -> str:
    sec = max(0, round(sec))
    if sec < 60:
        return f"{sec}秒"
    minutes = round(sec / 60)
    return f"{minutes}分"


def _people_names() -> dict[str, str]:
    """世話人の ID → 呼び名(家の config/people.json)。無ければ空"""
    try:
        raw = json.loads((DATA_DIR / "config" / "people.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        k: v["name"] for k, v in raw.items()
        if isinstance(v, dict) and isinstance(v.get("name"), str) and v["name"]
    }


def _setting_note(detail: dict, names: dict[str, str]) -> str:
    """体の設定「CAM TO」がだれになっていたかを添える。

    だれの手だったかは言わない(体には分からない)
    """
    who = detail.get("cam_to")
    if not isinstance(who, str) or not who:
        return ""
    return f"（設定は {names.get(who, who)}）"


def _format_events(events: list[dict]) -> list[str]:
    lines: list[str] = []
    pending_picked_up: dict | None = None
    names = _people_names()

    for record in events:
        ts = datetime.fromisoformat(record["ts"])
        hhmm = ts.strftime("%H:%M")
        etype = record.get("type")
        detail = record.get("detail", {})

        if etype == "picked_up":
            # put_down が続くかどうか、次のイベントを見てから判定する
            pending_picked_up = record
            continue

        if etype == "put_down":
            if pending_picked_up is not None:
                pu_hhmm = datetime.fromisoformat(pending_picked_up["ts"]).strftime("%H:%M")
                duration = _format_duration_sec(detail.get("carried_sec", 0))
                note = _setting_note(detail, names) or _setting_note(
                    pending_picked_up.get("detail", {}), names)
                lines.append(f"{pu_hhmm} 持ち上げられて、{duration}くらい運ばれた{note}")
                pending_picked_up = None
            else:
                lines.append(f"{hhmm} 下ろされた")
            continue

        # picked_up の直後に別種のイベントが来た＝まだ運ばれている途中でカーソルが来た
        if pending_picked_up is not None:
            pu_hhmm = datetime.fromisoformat(pending_picked_up["ts"]).strftime("%H:%M")
            lines.append(f"{pu_hhmm} 持ち上げられた")
            pending_picked_up = None

        if etype == "ambient_jump":
            before = detail.get("from")
            after = detail.get("to")
            direction = "明るい" if (after or 0) > (before or 0) else "暗い"
            lines.append(f"{hhmm} {direction}場所に移った（ambient {before}→{after}）")
        elif etype == "touch":
            count = detail.get("count", 1)
            strokes = detail.get("strokes", 0)
            taps = detail.get("taps", 0)
            note = _setting_note(detail, names)
            if strokes and taps:
                lines.append(f"{hhmm} 撫でられた（{strokes}回）、タッチされた（{taps}回）{note}")
            elif strokes:
                lines.append(f"{hhmm} 撫でられた（{strokes}回）{note}")
            else:
                lines.append(f"{hhmm} タッチされた（{taps or count}回）{note}")
        elif etype == "offline_gap":
            minutes = detail.get("minutes", 0)
            minutes_int = max(1, round(minutes))
            lines.append(f"{hhmm}から{minutes_int}分間、感覚がなかった")
        elif etype == "sleep":
            lines.append(f"{hhmm} 眠りについた")
        elif etype == "woken":
            lines.append(f"{hhmm} 眠っているところを起こされた")
        elif etype == "restarted":
            lines.append(f"{hhmm} 体が再起動した{RESTART_WHY.get(detail.get('reason'), '')}")
        elif etype == "battery_low":
            threshold = detail.get("threshold", "?")
            lines.append(f"電池が残り{threshold}%を切った")
        # 未知のイベント種別は無視（Phase 2/3 で追加される想定）

    # 末尾が picked_up のまま終わった（まだ持ち上げられ続けている）場合
    if pending_picked_up is not None:
        pu_hhmm = datetime.fromisoformat(pending_picked_up["ts"]).strftime("%H:%M")
        lines.append(f"{pu_hhmm} 持ち上げられた")

    return lines


def build_digest(character: str) -> tuple[list[str], datetime]:
    """(整形済みの行のリスト, 現在時刻) を返す。"""
    cursor = _read_cursor(character)
    events = _load_events(character, cursor)
    lines = _format_events(events)
    return lines, datetime.now()


def main() -> int:
    parser = argparse.ArgumentParser(description="体験バッファのダイジェストを表示する")
    parser.add_argument("--character", required=True, help="キャラクターID（例: puchiko）")
    parser.add_argument(
        "--mark-read", action="store_true", help="表示後にカーソルを現在時刻へ進める"
    )
    args = parser.parse_args()

    try:
        lines, now = build_digest(args.character)
    except Exception as e:  # 自律行動を絶対に壊さないためのガード
        print(f"[experience_digest error] {e}", file=sys.stderr)
        return 0

    for line in lines:
        print(line)

    if args.mark_read:
        try:
            _write_cursor(args.character, now)
        except OSError as e:
            print(f"[experience_digest cursor write error] {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
