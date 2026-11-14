#!/usr/bin/env python3
"""部屋の記録: SwitchBot の ハブ 2・温湿度計(気温・湿度・明るさ)、人感(動き)、電気(オン/オフ)を 10 分ごとに残す。

鍵は家の .env の SWITCHBOT_TOKEN / SWITCHBOT_SECRET(部品 m5-petit-switchbot と同じ)。置き場所は家の state/room/:

    state/room/YYYYMMDD.jsonl   1 行 = 1 回の読み {"ts": "...", "devices": {"<id>": {"name", "type", "temperature", "humidity", "light", "move", "power", "brightness"}}}
    state/room/latest.json      いちばん新しい 1 回(+ 人感が最後に動いた時刻 last_move)

記録する機器は、種類で自動(Hub 2・Meter・Motion Sensor・Color Bulb・Plug・Contact Sensor)。
家の config/room.json で、機体ごとのオン/オフ(設定ページの「SwitchBot 連携」)と名前の言い換え:

    {"off": ["…id…"], "names": {"…id…": "あり部屋"}, "omron": {"port": "/dev/omron-env", "name": "机(OMRON)"}}

PC に差した OMRON 2JCIE-BU01(scripts/omron_env.py)も、ポートがあれば id "omron-env" の 1 台として同じ記録に入る
(気温・湿度・明るさ・気圧・騒音・eCO2・eTVOC。2026-11-14)。SwitchBot の鍵が無くても OMRON だけで記録できる

使うところ:
- cron(10 分ごと): `room_log.py record`
- ダッシュボード: ようす の「部屋」カード(latest)、📅 よてい の日の欄(その日の最低・最高)
- ぷちへ 1 行(`room_log.py line`。30 分以内の読みだけ): 「家の空気: あり部屋 23.9℃・43%(明るさ 11)。ありさん机の動き: なし(最後は 18:05)。あり部屋の電気 オン」

Usage:
    python3 room_log.py record            # 読んで 1 行足す(失敗しても静かに終わる。cron 用)
    python3 room_log.py line [--character <id>]   # いまの 1 行(ぷちが見に行くとき。30 分以内。--character でいる部屋の機体を先に)
    python3 room_log.py changes --character <id> [--mark]   # 前に伝えた値から大きく動いたときだけ 1 行(ぷちに渡すのはこちら)
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
MOTION_NOTE = "人感は、座ったまま動かないと更新されない(動きなし = いない、ではない)"
OMRON_ID = "omron-env"            # PC に差した OMRON 2JCIE-BU01 の、機体としての id
OMRON_PORT = "/dev/omron-env"     # udev の決まり(99-omron-2jcie-bu.rules)が作る名前
OMRON_TYPE = "OMRON 2JCIE-BU"
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


def load_cfg(base: Path) -> dict:
    try:
        cfg = json.loads((base / "config" / "room.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    off = [x for x in (cfg.get("off") or []) if isinstance(x, str)]
    names = {k: str(v) for k, v in (cfg.get("names") or {}).items()} if isinstance(cfg.get("names"), dict) else {}
    om = cfg.get("omron") if isinstance(cfg.get("omron"), dict) else {}
    omron = {"port": str(om.get("port") or OMRON_PORT), "name": str(om.get("name") or names.get(OMRON_ID) or "PC の OMRON")}
    return {"off": off, "names": names, "omron": omron}


def set_off(base: Path, off: list[str]) -> dict:
    """記録しない機体の id を決める(設定ページの「SwitchBot 連携」)。名前の言い換えは残す"""
    cfg = load_cfg(base)
    cfg["off"] = sorted({x for x in off if isinstance(x, str) and x})
    try:   # 書くのは元の形のまま(omron は、元のファイルに書いてあったときだけ)
        raw = json.loads((base / "config" / "room.json").read_text(encoding="utf-8"))
        if not (isinstance(raw, dict) and isinstance(raw.get("omron"), dict)):
            cfg.pop("omron", None)
    except (OSError, json.JSONDecodeError):
        cfg.pop("omron", None)
    p = base / "config" / "room.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return cfg


def omron_present(cfg: dict) -> bool:
    return Path(cfg["omron"]["port"]).exists()


def read_omron(cfg: dict) -> dict | None:
    """PC に差した OMRON を 1 回読む(scripts/omron_env.py)。無い・読めないときは None"""
    if not omron_present(cfg):
        return None
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import omron_env
        d = omron_env.read(cfg["omron"]["port"])
    except Exception:
        return None
    return {"name": cfg["omron"]["name"], "type": OMRON_TYPE,
            **{k: d[k] for k in ("temperature", "humidity", "light", "pressure", "noise", "eco2", "etvoc") if k in d}}


def _switchbot_devices(base: Path) -> list[dict] | None:
    """SwitchBot の機体一覧。鍵が無い・つながらないときは None"""
    token, secret = _env(base, "SWITCHBOT_TOKEN"), _env(base, "SWITCHBOT_SECRET")
    if not token or not secret:
        return None
    try:
        return _get("/devices", token, secret).get("body", {}).get("deviceList", [])
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def devices(base: Path) -> list[dict] | None:
    """記録できる機体の一覧 [{id, name, type, on}](SwitchBot に 1 回聞く + PC の OMRON)。どちらも無いときは None"""
    cfg = load_cfg(base)
    found = _switchbot_devices(base)
    out = [{"id": d["deviceId"], "name": cfg["names"].get(d["deviceId"]) or d.get("deviceName") or d["deviceId"], "type": d.get("deviceType", ""),
            "on": d["deviceId"] not in cfg["off"]} for d in (found or []) if d.get("deviceId") and d.get("deviceType") in TYPES]
    if omron_present(cfg):
        out.append({"id": OMRON_ID, "name": cfg["omron"]["name"], "type": OMRON_TYPE, "on": OMRON_ID not in cfg["off"]})
    return out if (found is not None or out) else None


def read_all(base: Path) -> dict | None:
    """いまの読み(オンの機体だけ。SwitchBot + PC の OMRON)。どちらも読めないときは None"""
    cfg = load_cfg(base)
    off, names = set(cfg["off"]), cfg["names"]
    token, secret = _env(base, "SWITCHBOT_TOKEN"), _env(base, "SWITCHBOT_SECRET")
    devices_ = _switchbot_devices(base) or []
    out = {}
    if OMRON_ID not in off:
        om = read_omron(cfg)
        if om:
            out[OMRON_ID] = om
    for d in devices_:
        did, typ = d.get("deviceId"), d.get("deviceType")
        if not did or typ not in TYPES or did in off:
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
    _merge_presence(base, snap)
    tmp = rd / "latest.json.tmp"
    tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(rd / "latest.json")
    return snap


def presence_last_move(base: Path | None = None) -> dict[str, str]:
    """気配(presence_watch.py、1 分ごと)が覚えている、人感ごとの最後に動いた時刻。無ければ空"""
    try:
        raw = json.loads(((base or data_dir()) / "state" / "presence_state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {did: st["last_move"] for did, st in raw.items() if isinstance(st, dict) and st.get("last_move")}


def _merge_presence(base: Path | None, snap: dict) -> dict:
    """10 分ごとの読みでは、あいだの短い動きを見逃す(2026-11-14 ありさん「アプリでは 20:39 に動態検出」)。
    1 分ごとに見ている気配のほうが新しければ、そちらの時刻を使う"""
    lm = dict(snap.get("last_move") or {})
    for did, ts in presence_last_move(base).items():
        if ts > lm.get(did, ""):   # ISO の文字列は、そのまま前後が比べられる
            lm[did] = ts
    snap["last_move"] = lm
    return snap


def latest(base: Path | None = None) -> dict | None:
    """いちばん新しい読み。人感の最後の動きは、気配の記録のほうが新しければそちら"""
    try:
        snap = json.loads((room_dir(base) / "latest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _merge_presence(base, snap)


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
    """その日の、機器ごとの 気温・湿度・気圧・eCO2 の最低/最高、動いた回数、電気がオンだった回数"""
    rows = day_rows(base, day)
    per: dict[str, dict] = {}
    for r in rows:
        for did, dev in (r.get("devices") or {}).items():
            p = per.setdefault(did, {"name": dev.get("name", did), "type": dev.get("type", ""), "n": 0})
            p["n"] += 1
            for k in ("temperature", "humidity", "pressure", "eco2"):
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


def _my_room(base: Path | None, character_id: str | None) -> tuple[str, set[str]]:
    """その子の体がいる部屋と、その部屋の機体の id(scripts/spots.py)。分からなければ ("", set())"""
    if not character_id:
        return "", set()
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import spots
        b = spots.effective(base, character_id)
        return (b["room"], set(spots.room_devices(base, b["room"]))) if b else ("", set())
    except Exception:
        return "", set()


def line(base: Path | None = None, now: datetime | None = None, character_id: str | None = None) -> str:
    """いまの 1 行(30 分以内の読みだけ)。character_id があれば、その子がいる部屋の機体を先に「いる部屋」と付けて"""
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
    my_room, mine = _my_room(base, character_id)
    air, move, power = [], [], []
    ordered = sorted(snap["devices"].items(), key=lambda kv: kv[0] not in mine)
    for did, dev in ordered:
        name = dev.get("name", did) + ("(いる部屋)" if did in mine else "")
        if "temperature" in dev:
            air.append(f"{name} {dev['temperature']}℃" + (f"・{dev['humidity']}%" if "humidity" in dev else "")
                       + (f"・気圧 {dev['pressure']} hPa" if "pressure" in dev else "") + (f"・CO2 {dev['eco2']} ppm" if "eco2" in dev else "")
                       + (f"(明るさ {dev['light']})" if "light" in dev else ""))
        if "move" in dev:
            last = (snap.get("last_move") or {}).get(did)
            tail = "" if dev["move"] else (f"(最後は {_hm(last)})" if last else "(記録を始めてから、まだ動きなし)")
            move.append(f"{name}の動き: {'あり' if dev['move'] else 'なし'}" + tail)
        if "power" in dev:
            power.append(f"{name} {'オン' if dev['power'] == 'on' else 'オフ'}")
    parts = []
    if air:
        parts.append("、".join(air))
    if move:
        # 「動きなし」には但し書き(2026-11-14 ありさん: 机に座りっぱなしで動かないと更新されないことも伝えたい)
        parts.append("、".join(move) + (f"。{MOTION_NOTE}" if any("なし" in m for m in move) else ""))
    if power:
        parts.append("、".join(power))
    head = f"家の空気(いる部屋は {my_room}): " if my_room else "家の空気: "
    return head + "。".join(parts) + f"({_hm(snap['ts'])} の読み)" if parts else ""


TEMP_STEP = 2.0    # これ以上動いたら「変わった」(℃)
HUMID_STEP = 10    # 同(%)
PRESS_STEP = 3.0   # 同(hPa。低気圧が近づく・離れる目安)
CO2_HIGH = 1000    # eCO2 がこれを超えたら一言(2026-11-14 ぷちこの希望。換気の目安)
CO2_LOW = 800      # 超えたあと、ここまで下がったら「戻った」


def _wants(character_id: str, base: Path | None) -> dict[str, bool]:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import notices
        return notices.enabled(character_id, base)
    except Exception:
        return {"temperature": True, "humidity": True, "pressure": True, "co2": True}


def change_line(base: Path | None, character_id: str, mark: bool = False, now: datetime | None = None) -> str:
    """前にその子に伝えた値から、気温が TEMP_STEP・湿度が HUMID_STEP・気圧が PRESS_STEP 以上動いた機体だけ 1 行(ぷちたちの希望: 変わったときだけ)。
    はじめての回は、いまの値を覚えるだけで何も言わない。伝えたことは characters/<id>/state/room_told.json"""
    base = base or data_dir()
    snap = latest(base)
    if not snap:
        return ""
    now = now or datetime.now()
    try:
        if (now - datetime.fromisoformat(snap["ts"])).total_seconds() / 60 > FRESH_MIN:
            return ""
    except (TypeError, ValueError):
        return ""
    told_path = base / "characters" / character_id / "state" / "room_told.json"
    try:
        told = json.loads(told_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        told = None
    cur = {did: {k: dev[k] for k in ("temperature", "humidity", "pressure", "eco2") if k in dev} for did, dev in snap["devices"].items()}
    cur = {k: v for k, v in cur.items() if v}
    want = _wants(character_id, base)   # その子が受け取る種類(scripts/notices.py)。受け取らない種類は比べない(値は覚える)
    changes = []
    if isinstance(told, dict):
        for did, vals in cur.items():
            old = told.get(did) or {}
            name = snap["devices"][did].get("name", did)
            bits = []
            if want["temperature"] and "temperature" in vals and isinstance(old.get("temperature"), (int, float)) and abs(vals["temperature"] - old["temperature"]) >= TEMP_STEP:
                bits.append(f"{old['temperature']}℃ → {vals['temperature']}℃")
            if want["humidity"] and "humidity" in vals and isinstance(old.get("humidity"), (int, float)) and abs(vals["humidity"] - old["humidity"]) >= HUMID_STEP:
                bits.append(f"湿度 {old['humidity']}% → {vals['humidity']}%")
            if want["pressure"] and "pressure" in vals and isinstance(old.get("pressure"), (int, float)) and abs(vals["pressure"] - old["pressure"]) >= PRESS_STEP:
                bits.append(f"気圧 {old['pressure']} → {vals['pressure']} hPa" + ("(下がってきた)" if vals["pressure"] < old["pressure"] else "(上がってきた)"))
            # CO2 は「境を越えたとき」だけ: 前に伝えた値が 1000 以下で いま 1000 超 → 超えた。前が 1000 超で いま 800 以下 → 戻った
            if want.get("co2", True) and "eco2" in vals and isinstance(old.get("eco2"), (int, float)):
                if old["eco2"] <= CO2_HIGH < vals["eco2"]:
                    bits.append(f"CO2 が {CO2_HIGH} ppm を超えた({vals['eco2']} ppm。換気の目安)")
                elif old["eco2"] > CO2_HIGH and vals["eco2"] <= CO2_LOW:
                    bits.append(f"CO2 が戻った({vals['eco2']} ppm)")
            if bits:
                changes.append(f"{name} " + "、".join(bits))
    if mark and (changes or told is None):
        # 伝えた(か、はじめて覚えた)値だけ更新。変わっていない機体は前の値のまま(小さな動きの積み重ねも、いつか「変わった」になる)
        new_told = dict(told) if isinstance(told, dict) else {}
        for did, vals in cur.items():
            if told is None or any(c.startswith(snap["devices"][did].get("name", did) + " ") for c in changes):
                new_told[did] = vals
        told_path.parent.mkdir(parents=True, exist_ok=True)
        told_path.write_text(json.dumps(new_told, ensure_ascii=False) + "\n", encoding="utf-8")
    return ("家の空気が変わった: " + "。".join(changes) + f"({_hm(snap['ts'])} の読み)") if changes else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("record")
    p = sub.add_parser("line")
    p.add_argument("--character", default=None)
    p = sub.add_parser("changes")
    p.add_argument("--character", required=True)
    p.add_argument("--mark", action="store_true")
    p = sub.add_parser("day")
    p.add_argument("--date", required=True)
    a = ap.parse_args()
    base = data_dir()
    if a.cmd == "record":
        snap = record(base)
        print(f"[room] {len(snap['devices'])} 台を記録" if snap else "[room] 読めなかった(鍵が無い・つながらない)")
    elif a.cmd == "line":
        text = line(base, character_id=a.character)
        if text:
            print(text)
    elif a.cmd == "changes":
        text = change_line(base, a.character, mark=a.mark)
        if text:
            print(text)
    else:
        print(json.dumps(day_summary(base, a.date), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
