#!/usr/bin/env python3
"""「いまから n 時間は、active time の外でも自律行動してよい」(2026-11-16 ありさん)。

置き場所は その子の characters/<id>/config/settings.json:

    {"awake": {"until": "2026-11-16T22:30"}}

- until まで、active time の外でも、いつもの cron の枠(30 分ごと)で自律行動する。active time の中では何も変わらない
- 過ぎたら自然に ふだん通り(active time だけ)に戻る。消す必要はない
- 判定は autonomous-action.sh が settings.json の awake.until を見る(分までの ISO 文字列の大小比べ)
- からだ おやすみ(body_switches.py の rest)とは別。おやすみ中でも、動くか・動かないかは変えない

Usage:
    python3 awake.py show --character <id>
    python3 awake.py set --character <id> --hours 3      # --off でやめる
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import body_switches as bs  # noqa: E402  settings.json の読み書きは からだ おやすみ と同じ

MAX_HOURS = 24


def until_of(settings: dict, now: datetime | None = None) -> datetime | None:
    """いま有効な until(過ぎていたら None)"""
    now = now or datetime.now()
    aw = settings.get("awake") if isinstance(settings.get("awake"), dict) else {}
    try:
        until = datetime.fromisoformat(aw.get("until") or "")
    except ValueError:
        return None
    return until if until > now else None


def view(settings: dict, now: datetime | None = None) -> dict:
    until = until_of(settings, now)
    return {"on": bool(until), "until": until.strftime("%H:%M") if until else "",
            "until_iso": until.isoformat(timespec="minutes") if until else ""}


def set_awake(character_id: str, hours: float | None, base: Path | None = None, now: datetime | None = None) -> dict:
    """いまから hours 時間(None・0 でやめる)。settings.json の awake.until だけ書き換える"""
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    if hours is not None and not (0 <= hours <= MAX_HOURS):
        raise ValueError(f"時間は 0〜{MAX_HOURS}")
    p = bs.settings_path(character_id, base)
    s = bs.load_settings(character_id, base)
    aw = dict(s.get("awake") or {}) if isinstance(s.get("awake"), dict) else {}
    if hours:
        aw["until"] = (now + timedelta(hours=hours)).isoformat(timespec="minutes")
    else:
        aw.pop("until", None)
    s["awake"] = aw
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("show", "set"):
        sp = sub.add_parser(name)
        sp.add_argument("--character", required=True)
        if name == "set":
            sp.add_argument("--hours", type=float, default=None)
            sp.add_argument("--off", action="store_true")
    a = ap.parse_args()
    base = bs.data_dir()
    if a.cmd == "show":
        print(json.dumps(view(bs.load_settings(a.character, base)), ensure_ascii=False))
    else:
        s = set_awake(a.character, None if a.off else a.hours, base)
        print(json.dumps(view(s), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
