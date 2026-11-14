#!/usr/bin/env python3
"""部屋の記録: SwitchBot の ハブ 2・温湿度計(気温・湿度・明るさ)、人感(動き)、電気(オン/オフ)を 10 分ごとに残す。

鍵は家の .env の SWITCHBOT_TOKEN / SWITCHBOT_SECRET(部品 m5-petit-switchbot と同じ)。置き場所は家の state/room/:

    state/room/YYYYMMDD.jsonl   1 行 = 1 回の読み {"ts": "...", "devices": {"<id>": {"name", "type", "temperature", "humidity", "light", "move", "power", "brightness"}}}
    state/room/latest.json      いちばん新しい 1 回(+ 人感が最後に動いた時刻 last_move)

記録する機器は、種類で自動(Hub 2・Meter・Motion Sensor・Color Bulb・Plug・Contact Sensor)。
家の config/room.json があれば、その id だけ / 名前の言い換え:

    {"only": ["…id…"], "names": {"…id…": "あり部屋"}}

使うところ:
- cron(10 分ごと): `room_log.py record`
- ダッシュボード: ようす の「部屋」カード(latest)、📅 よてい の日の欄(その日の最低・最高)
- ぷちへ 1 行(`room_log.py line`。30 分以内の読みだけ): 「家の空気: あり部屋 23.9℃・43%(明るさ 11)。ありさん机の動き: なし(最後は 18:05)。あり部屋の電気 オン」

Usage:
    python3 room_log.py record            # 読んで 1 行足す(失敗しても静かに終わる。cron 用)
    python3 room_log.py line              # ぷちに渡す 1 行(無ければ何も出さない)
    python3 room_log.py day --date YYYY-MM-DD   # その日のまとめ(JSON)
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
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

API = "https://api.switch-bot.com/v1.1"
TYPES = {"Hub 2", "Meter", "MeterPlus", "WoIOSensor", "Motion Sensor", "Color Bulb", "Strip Light", "Ceiling Light",
         "Plug", "Plug Mini (JP)", "Plug Mini (US)", "Contact Sensor"}
FRESH_MIN = 30        # ぷちに渡すのは、これより新しい読みだけ
TIMEOUT = 10


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def room_dir(base: Path | None = None) -> Path:
    return (base or data_dir()) / "state" / "room"


def _env(base: Path, key: str) -> str | None:
    if os.environ.get(key):
        return os.environ[key]
    try:
        for line in (base / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def _headers(token: str, secret: str) -> dict:
    t = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4())
    sign = base64.b64encode(hmac.new(secret.encode(), f"{token}{t}{nonce}".encode(), hashlib.sha256).digest()).decode()
    return {"Authorization": token, "sign": sign, "t": t, "nonce": nonce, "Content-Type": "application/json"}


def _get(path: str, token: str, secret: str) -> dict:
    req = urllib.request.Request(API + path, headers=_headers(token, secret))
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:   # noqa: S310
        return json.loads(r.read().decode("utf-8"))


def pick(status: dict) -> dict:
    """機器の status から、残す項目だけ"""
    out = {}
    if isinstance(status.get("temperature"), (int, float)):
        out["temperature"] = status["temperature"]
    if isinstance(status.get("humidity"), (int, float)):
        out["humidity"] = status["humidity"]
    if isinstance(status.get("lightLevel"), (int, float)):
        out["light"] = status["lightLevel"]
    if isinstance(status.get("moveDetected"), bool):
        out["move"] = status["moveDetected"]
    if isinstance(status.get("brightness"), str) and "move" in out:   # 人感の明るさ(bright / dim)
        out["light_word"] = status["brightness"]
    if status.get("power") in ("on", "off"):
        out["power"] = status["power"]
    if isinstance(status.get("brightness"), (int, float)):
        out["brightness"] = status["brightness"]
    if status.get("openState") in ("open", "close", "timeOutNotClose"):
        out["open"] = status["openState"]
    return out


def read_all(base: Path) -> dict | None:
    """いまの読み。鍵が無い・つながらないときは None"""
    token, secret = _env(base, "SWITCHBOT_TOKEN"), _env(base, "SWITCHBOT_SECRET")
    if not token or not secret:
        return None
    try:
        cfg = json.loads((base / "config" / "room.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cfg = {}
    only = set(cfg.get("only") or [])
    names = cfg.get("names") or {}
    try:
        devices = _get("/devices", token, secret).get("body", {}).get("deviceList", [])
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    out = {}
    for d in devices:
        did, typ = d.get("deviceId"), d.get("deviceType")
        if not did or typ not in TYPES or (only and did not in only):
            continue
        try:
            st = _get(f"/devices/{did}/status", token, secret).get("body", {})
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            continue
        out[did] = {"name": names.get(did) or d.get("deviceName") or did, "type": typ, **pick(st)}
    return {"ts": datetime.now().replace(microsecond=0).isoformat(), "devices": out} if out else None


def record(base: Path | None = None) -> dict | None:
    base = base or data_dir()
    snap = read_all(base)
    if not snap:
        return None
    rd = room_dir(base)
    rd.mkdir(parents=True, exist_ok=True)
    day = datetime.fromisoformat(snap["ts"]).strftime("%Y%m%d")
    with (rd / f"{day}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(snap, ensure_ascii=False) + "\n")
    # 人感が最後に動いた時刻は、latest に持ち越す
    prev = latest(base) or {}
    last_move = dict(prev.get("last_move") or {})
    for did, dev in snap["devices"].items():
        if dev.get("move"):
            last_move[did] = snap["ts"]
    snap["last_move"] = last_move
    tmp = rd / "latest.json.tmp"
    tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(rd / "latest.json")
    return snap


def latest(base: Path | None = None) -> dict | None:
    try:
        return json.loads((room_dir(base) / "latest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def day_rows(base: Path | None, day: datetime | str) -> list[dict]:
    key = day if isinstance(day, str) else day.strftime("%Y%m%d")
    key = key.replace("-", "")
    try:
        lines = (room_dir(base) / f"{key}.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def day_summary(base: Path | None, day: str) -> dict:
    """その日の、機器ごとの 気温・湿度の最低/最高、動いた回数、電気がオンだった回数"""
    rows = day_rows(base, day)
    per: dict[str, dict] = {}
    for r in rows:
        for did, dev in (r.get("devices") or {}).items():
            p = per.setdefault(did, {"name": dev.get("name", did), "type": dev.get("type", ""), "n": 0})
            p["n"] += 1
            for k in ("temperature", "humidity"):
                if isinstance(dev.get(k), (int, float)):
                    p[k + "_min"] = min(p.get(k + "_min", dev[k]), dev[k])
                    p[k + "_max"] = max(p.get(k + "_max", dev[k]), dev[k])
            if dev.get("move"):
                p["moves"] = p.get("moves", 0) + 1
            if dev.get("power") == "on":
                p["on"] = p.get("on", 0) + 1
    return {"date": day, "reads": len(rows), "devices": per}


def _hm(ts: str) -> str:
    try:
        t = datetime.fromisoformat(ts)
        return f"{t.hour}:{t.minute:02d}"
    except (TypeError, ValueError):
        return ""


def line(base: Path | None = None, now: datetime | None = None) -> str:
    """ぷちに渡す 1 行(30 分以内の読みだけ)"""
    snap = latest(base)
    if not snap:
        return ""
    now = now or datetime.now()
    try:
        age = (now - datetime.fromisoformat(snap["ts"])).total_seconds() / 60
    except (TypeError, ValueError):
        return ""
    if age > FRESH_MIN:
        return ""
    air, move, power = [], [], []
    for did, dev in snap["devices"].items():
        name = dev.get("name", did)
        if "temperature" in dev:
            air.append(f"{name} {dev['temperature']}℃" + (f"・{dev['humidity']}%" if "humidity" in dev else "") + (f"(明るさ {dev['light']})" if "light" in dev else ""))
        if "move" in dev:
            last = (snap.get("last_move") or {}).get(did)
            move.append(f"{name}の動き: {'あり' if dev['move'] else 'なし'}" + (f"(最後は {_hm(last)})" if last and not dev["move"] else ""))
        if "power" in dev:
            power.append(f"{name} {'オン' if dev['power'] == 'on' else 'オフ'}")
    parts = []
    if air:
        parts.append("、".join(air))
    if move:
        parts.append("、".join(move))
    if power:
        parts.append("、".join(power))
    return "家の空気: " + "。".join(parts) + f"({_hm(snap['ts'])} の読み)" if parts else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("record")
    sub.add_parser("line")
    p = sub.add_parser("day")
    p.add_argument("--date", required=True)
    a = ap.parse_args()
    base = data_dir()
    if a.cmd == "record":
        snap = record(base)
        print(f"[room] {len(snap['devices'])} 台を記録" if snap else "[room] 読めなかった(鍵が無い・つながらない)")
    elif a.cmd == "line":
        text = line(base)
        if text:
            print(text)
    else:
        print(json.dumps(day_summary(base, a.date), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
