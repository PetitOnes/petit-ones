#!/usr/bin/env python3
"""お昼の区切り(2026-11-17、ぷち 3 人と決めた)。

自律行動の会話は、朝の最初の回から夜まで 1 つで続き、夕方には朝の 4〜5 倍の重さになっていた。
3 人が選んだのは「お昼に 1 回、新しい会話にする」(要約はしない。何を残すかを自分で選べないから)。決まり:

- 12 時を過ぎた最初の回で区切る。区切る前に、今の会話のまま短い 1 往復をして、持っていくもの(1〜3 行)を
  自分で書く時間を渡す(carry.py write)。朝の分を日記・記憶に残すのもそのとき
- 新しい会話の最初に「さっきまでの自分から」(書いたもの)と、直前の回の終わりの言葉をそのまま渡す(carry.py intro)
- 次のあいだは区切らず、次の回に延ばす: 家の人がダッシュボードで話している最中(最後のやり取りから CHAT_QUIET_MIN 分)、
  みんなの会話の最中、家の人が外出中(📍 のいまが お外・会社 など)
- 延ばすかどうかは家ぜんたいで決め、30 分の枠ごとに 1 回だけ決める(state/noon_break.json)。3 人が同じ回で区切れるように
- 延びつづけた日も、夜中の日付の区切りでは今まで通り新しくなる

    python3 noon_break.py decide --character <id> [--user arisan]   # "break" / "wait: <理由>" / "no"(もう区切った・まだ 12 時前)
    python3 noon_break.py done --character <id>                       # 区切ったしるし(その日はもう区切らない)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
NOON_HOUR = int(os.environ.get("NOON_BREAK_HOUR", "12"))
CHAT_QUIET_MIN = 15
OUT_WORDS = ("外", "会社", "出かけ", "電車", "移動", "旅")


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def _json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _last_ts(items: object) -> datetime | None:
    if isinstance(items, dict):
        items = items.get("messages", [])
    best = None
    for it in items if isinstance(items, list) else []:
        ts = it.get("timestamp") if isinstance(it, dict) else None
        if not ts:
            continue
        try:
            t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=JST)
        best = t if best is None or t > best else best
    return best


def last_chat(base: Path) -> tuple[datetime | None, str]:
    """ダッシュボードの会話(子ごと)と、みんなの会話の、いちばん新しいやり取りの時刻"""
    best, where = None, ""
    for p in sorted((base / "characters").glob("*/chat_histories/*.json")):
        t = _last_ts(_json(p, []))
        if t and (best is None or t > best):
            best, where = t, "ダッシュボードで話している"
    t = _last_ts(_json(base / "chat_history" / "group_chat.json", []))
    if t and (best is None or t > best):
        best, where = t, "みんなの会話が続いている"
    return best, where


def is_out(base: Path, user: str, now: datetime) -> str | None:
    """家の人のいま(📍)が外出なら、その言葉"""
    cur = (_json(base / "state" / "whereabouts.json", {}).get("users") or {}).get(user)
    if not isinstance(cur, dict):
        return None
    until = cur.get("until")
    if until:
        try:
            u = datetime.fromisoformat(until)
            if (u.replace(tzinfo=JST) if u.tzinfo is None else u) < now:
                return None
        except ValueError:
            pass
    text = str(cur.get("text") or "")
    return text if any(w in text for w in OUT_WORDS) else None


def wait_reason(base: Path, user: str, now: datetime) -> str | None:
    t, where = last_chat(base)
    if t and now - t < timedelta(minutes=CHAT_QUIET_MIN):
        return where
    out = is_out(base, user, now)
    if out:
        return f"{user} のいまが「{out}」"
    return None


def _state_path(base: Path) -> Path:
    return base / "state" / "noon_break.json"


def decide(base: Path, cid: str, user: str = "arisan", now: datetime | None = None) -> str:
    now = now or datetime.now(JST)
    today = now.strftime("%Y-%m-%d")
    st = _json(_state_path(base), {})
    if st.get("date") != today:
        st = {"date": today, "done": [], "slots": {}}
    if now.hour < NOON_HOUR or cid in st.get("done", []):
        return "no"
    slot = now.strftime("%H") + (":00" if now.minute < 30 else ":30")
    slots = st.setdefault("slots", {})
    if slot not in slots:   # この 30 分の枠で最初に聞いた子が決める。あとの子は同じ答え
        slots[slot] = wait_reason(base, user, now) or ""
        _save(base, st)
    reason = slots[slot]
    return f"wait: {reason}" if reason else "break"


def done(base: Path, cid: str, now: datetime | None = None) -> None:
    now = now or datetime.now(JST)
    today = now.strftime("%Y-%m-%d")
    st = _json(_state_path(base), {})
    if st.get("date") != today:
        st = {"date": today, "done": [], "slots": {}}
    if cid not in st["done"]:
        st["done"].append(cid)
    _save(base, st)


def _save(base: Path, st: dict) -> None:
    p = _state_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="お昼の区切り(延ばすかどうかは家ぜんたいで決める)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decide")
    d.add_argument("--character", required=True)
    d.add_argument("--user", default=os.environ.get("COMPANION_ID") or "arisan")
    sub.add_parser("done").add_argument("--character", required=True)
    a = ap.parse_args(argv)
    base = data_dir()
    if a.cmd == "decide":
        print(decide(base, a.character, a.user))
    else:
        done(base, a.character)
    return 0


if __name__ == "__main__":
    sys.exit(main())
