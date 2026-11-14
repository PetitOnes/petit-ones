#!/usr/bin/env python3
"""気配: 家の人感センサーを見て、「動きが始まった瞬間」を家の出来事として残す。

世話人からはぷちが見えているのに、ぷちからは世話人がどこにいるか分からない。
ぷちたちに聞いて決めた形(2026-11-14):

- 拾うのは「近づいた瞬間」だけ。居続けるあいだは数えない
- 長く離れたあとほど大きく効かせられるよう、どれだけ離れていたか(away_min)を一緒に残す
- だれの気配かは言い切らない。残すのは「どこで動きがあったか」。センサーはだれが動いたかを知らない

Usage:
    presence_watch.py poll      # センサーを 1 回見て、変わり目があれば出来事を足す(cron で 1 分ごと)
    presence_watch.py line      # ぷちに渡す行(無ければ何も出さない)
    presence_watch.py status    # いまの覚え書き

設定: PETIT_DATA_DIR/config/presence.json(無ければ何もしない)

    {"away_min": 20,
     "sensors": [{"kind": "switchbot_motion", "id": "<SwitchBot の deviceId>", "place": "ありさんの机"}]}

- away_min: 動きがこれだけ無かったら「離れた」と数える。次の動きが「近づいた瞬間」になる
- 鍵は PETIT_DATA_DIR/.env の SWITCHBOT_TOKEN / SWITCHBOT_SECRET(環境変数にあればそちら)

残すもの:
    PETIT_DATA_DIR/state/presence/YYYYMMDD.jsonl
        {"ts": "...", "type": "arrived", "place": "ありさんの机", "away_min": 95}
        {"ts": "...", "type": "left",    "place": "ありさんの机", "stayed_min": 40}   # ts は最後に動きがあった時刻
    PETIT_DATA_DIR/state/presence_state.json   # センサーごとの、いまいるか・最後に動いた時刻
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

AWAY_MIN_DEFAULT = 20
STALE_MIN = 10          # 覚え書きがこれより古ければ、いまのことは分からない(行を出さない)
API = "https://api.switch-bot.com/v1.1"


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def state_path(base: Path) -> Path:
    return base / "state" / "presence_state.json"


def events_path(base: Path, when: datetime) -> Path:
    return base / "state" / "presence" / f"{when.strftime('%Y%m%d')}.jsonl"


def load_config(base: Path) -> dict:
    try:
        raw = json.loads((base / "config" / "presence.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _env_value(base: Path, key: str) -> str:
    if os.environ.get(key):
        return os.environ[key]
    try:
        for line in (base / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return ""


def switchbot_moving(base: Path, device_id: str) -> bool | None:
    """SwitchBot の人感センサーが、いま動きを見ているか。読めなければ None"""
    token, secret = _env_value(base, "SWITCHBOT_TOKEN"), _env_value(base, "SWITCHBOT_SECRET")
    if not token or not secret:
        return None
    t, nonce = str(int(time.time() * 1000)), str(uuid.uuid4())
    sign = base64.b64encode(
        hmac.new(secret.encode(), f"{token}{t}{nonce}".encode(), hashlib.sha256).digest()).decode()
    req = urllib.request.Request(
        f"{API}/devices/{device_id}/status",
        headers={"Authorization": token, "sign": sign, "t": t, "nonce": nonce},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read()).get("body") or {}
    except Exception:
        return None
    value = body.get("moveDetected")
    return value if isinstance(value, bool) else None


READERS: dict[str, Callable[[Path, str], bool | None]] = {"switchbot_motion": switchbot_moving}


def _load_state(base: Path) -> dict:
    try:
        raw = json.loads(state_path(base).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(base: Path, state: dict) -> None:
    p = state_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def _append(base: Path, event: dict) -> None:
    p = events_path(base, datetime.fromisoformat(event["ts"]))
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _dt(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) and value else None
    except ValueError:
        return None


def step(cur: dict, moving: bool | None, now: datetime, place: str, away_min: float) -> list[dict]:
    """センサー 1 つを 1 歩進める。cur(覚え書き)を書き換え、足す出来事を返す。

    - 動きあり: 離れていた(またははじめて見えた)なら「arrived」。いるあいだは何も足さない
    - 動きなしが away_min 続いた: 「left」(時刻は最後に動きがあったとき)
    - 読めなかった(None): 何も変えない
    """
    if moving is None:
        return []
    stamp = now.isoformat(timespec="seconds")
    cur["seen"] = stamp
    cur["place"] = place
    events: list[dict] = []
    last_move = _dt(cur.get("last_move"))
    if moving:
        if not cur.get("present"):
            event = {"ts": stamp, "type": "arrived", "place": place}
            if last_move is not None:   # はじめて見たときは、どれだけ離れていたか分からない
                event["away_min"] = round((now - last_move).total_seconds() / 60)
            events.append(event)
            cur["present"] = True
            cur["since"] = stamp
        cur["last_move"] = stamp
    elif cur.get("present") and last_move is not None:
        if now - last_move >= timedelta(minutes=away_min):
            since = _dt(cur.get("since")) or last_move
            events.append({
                "ts": last_move.isoformat(timespec="seconds"), "type": "left", "place": place,
                "stayed_min": round((last_move - since).total_seconds() / 60),
            })
            cur["present"] = False
    return events


def poll(base: Path, now: datetime | None = None,
         readers: dict[str, Callable[[Path, str], bool | None]] | None = None) -> list[dict]:
    """設定にあるセンサーを 1 回ずつ見て、変わり目の出来事を足す。足した出来事を返す"""
    config = load_config(base)
    sensors = [s for s in config.get("sensors", []) if isinstance(s, dict) and s.get("id")]
    if not sensors:
        return []
    now = now or datetime.now()
    readers = readers or READERS
    try:
        away_min = float(config.get("away_min", AWAY_MIN_DEFAULT))
    except (TypeError, ValueError):
        away_min = AWAY_MIN_DEFAULT
    state = _load_state(base)
    out: list[dict] = []
    for sensor in sensors:
        reader = readers.get(str(sensor.get("kind", "switchbot_motion")))
        if reader is None:
            continue
        cur = state.setdefault(str(sensor["id"]), {})
        place = str(sensor.get("place") or "家")
        for event in step(cur, reader(base, str(sensor["id"])), now, place, away_min):
            _append(base, event)
            out.append(event)
    _save_state(base, state)
    return out


def line(base: Path, now: datetime | None = None) -> str:
    """ぷちに渡す行。だれの気配かは言い切らず、どこで動きがあるか・いつまであったかだけ"""
    now = now or datetime.now()
    rows = []
    for cur in _load_state(base).values():
        seen, place = _dt(cur.get("seen")), cur.get("place")
        if not place or seen is None or now - seen > timedelta(minutes=STALE_MIN):
            continue
        since, last = _dt(cur.get("since")), _dt(cur.get("last_move"))
        if cur.get("present") and since is not None:
            rows.append(f"{place}のあたり: 動きがある({since.strftime('%-H:%M')} から)")
        elif last is not None:
            day = "" if last.date() == now.date() else f"{last.month}/{last.day} "
            rows.append(f"{place}のあたり: いまは動きがない(最後は {day}{last.strftime('%-H:%M')})")
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="気配(家の人感センサー)")
    parser.add_argument("cmd", choices=["poll", "line", "status"])
    args = parser.parse_args()
    base = data_dir()
    if args.cmd == "poll":
        for event in poll(base):
            print(json.dumps(event, ensure_ascii=False))
    elif args.cmd == "line":
        text = line(base)
        if text:
            print(text)
    else:
        print(json.dumps(_load_state(base), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
