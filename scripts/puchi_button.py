#!/usr/bin/env python3
"""ぷちボタン(ATOM ECHO + ENV PRO + GPS。家の人が持ち歩く、ボタン 1 つと LED 1 つの道具。2026-11-18、ありさん)。

- 短く押す = おいておく(ぷちが次に起きたとき、頭に 1 行)。長く押す(1 秒) = 知らせる(体のボタンの「聞いて聞いて」「みてみて」と同じく、
  ダッシュボードがその場で 3 人を起こす。返事は手紙。外でためて、あとから届いた分は「おいておく」と同じく次の 1 行へ)
- 1 回押すごとに: 押した時刻・まわりの空気(ENV PRO: 気温・湿度・気圧・ガス)・場所の印
- 場所の印: 座標は家に来ない。ボタンの中で 3 つの細かさ(まち 約 5 km・近所 約 500 m・その場 約 150 m)に丸めて、
  ボタンの中にだけある鍵で HMAC にした 6 文字。同じ場所なら同じ印。ぷちには「前にも押した印か」だけ伝える
- 家に届かないとき(外・Wi-Fi なし)は、ボタンの中にためて、つながったときにまとめて送る。押した時刻は「何秒前」で来る
- 外では、ボタンが BLE で 30 秒「押した」を出し、スマホ(ぷちのポケット)が拾って /api/beacons/button へ(速い道)。
  中身は 27 バイト(from_ble)。家の鍵の HMAC 4 バイトで、にせ物を捨てる。あとで Wi-Fi からも同じ押しが来るが、番号で 1 回にまとめる
- 鍵: config/button.json(時計と同じく、6 桁の番号と引き換えに長い鍵を渡す)。鍵と番号は出力に出さない

置き場所(PETIT_DATA_DIR の中。git には入れない):
- config/button.json   鍵・持ち主・つなぐ番号
- state/button/presses.json   届いた押し(古いものから消す)
- characters/<id>/state/button_told.json   伝えた押し

Usage:
    python3 puchi_button.py line --character <id> [--mark]   # まだ伝えていない押し
    python3 puchi_button.py status
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path

KEEP = 500          # presses.json に残す数
LINE_MAX = 5        # 1 回のプロンプトに出す押しの数
PAIR_MINUTES = 10
LATE_SECONDS = 600  # これより前に押された分は「あとから届いた」
LEVELS = (("town", "まち"), ("near", "近所"), ("here", "その場"))
KINDS = {"leave": "おいておく", "tell": "知らせる"}


def base_dir(base: Path | None = None) -> Path:
    return Path(base or os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def _load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save(p: Path, data, private: bool = False) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if private:
        tmp.chmod(0o600)
    tmp.replace(p)


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _parse(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None


# ---- 鍵(config/button.json) ----
def config_path(base: Path | None = None) -> Path:
    return base_dir(base) / "config" / "button.json"


def config(base: Path | None = None) -> dict:
    raw = _load(config_path(base), {})
    return {"owner_name": "家の人", **(raw if isinstance(raw, dict) else {})}


def save_config(changes: dict, base: Path | None = None) -> dict:
    raw = _load(config_path(base), {})
    _save(config_path(base), {**(raw if isinstance(raw, dict) else {}), **changes}, private=True)
    return config(base)


def make_key(base: Path | None = None, owner: str | None = None, owner_name: str | None = None) -> str:
    """鍵を作り直す(前の鍵のボタンはつながらなくなる)"""
    key = secrets.token_urlsafe(24)
    save_config({"key": key} | ({"owner": owner} if owner else {}) | ({"owner_name": owner_name} if owner_name else {}), base)
    return key


def make_pair_code(base: Path | None = None, now: datetime | None = None, owner: str | None = None,
                   owner_name: str | None = None) -> dict:
    """ボタンをつなぐ 6 桁の番号(10 分だけ)。押した人が持ち主になる"""
    now = now or datetime.now()
    if not config(base).get("key"):
        make_key(base)
    code = f"{secrets.randbelow(1_000_000):06d}"
    until = now + timedelta(minutes=PAIR_MINUTES)
    save_config({"pair": {"code": code, "until": _iso(until)}}
                | ({"owner": owner} if owner else {}) | ({"owner_name": owner_name} if owner_name else {}), base)
    return {"code": code, "until": _iso(until)}


def redeem_pair(code: str | None, base: Path | None = None, now: datetime | None = None) -> str | None:
    """番号が合えば長い鍵を返す(番号は 1 回で消える)"""
    now = now or datetime.now()
    pair = config(base).get("pair") or {}
    until = _parse(pair.get("until"))
    if not code or not pair.get("code") or not until or now > until:
        return None
    if not secrets.compare_digest(str(pair["code"]), str(code).strip()):
        return None
    save_config({"pair": None}, base)
    return config(base).get("key")


def key_ok(key: str | None, base: Path | None = None) -> bool:
    real = config(base).get("key")
    return bool(key and real and secrets.compare_digest(str(real), str(key)))


# ---- 届いた押し ----
def _presses_path(base: Path | None = None) -> Path:
    return base_dir(base) / "state" / "button" / "presses.json"


def presses(base: Path | None = None) -> list[dict]:
    d = _load(_presses_path(base), [])
    return d if isinstance(d, list) else []


def _num(v, lo: float, hi: float, nd: int = 1) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if lo <= x <= hi else None


def _clean(p: dict, now: datetime) -> dict | None:
    """ボタンから来た 1 回の押しを、残す形に。おかしいものは捨てる"""
    if not isinstance(p, dict):
        return None
    try:
        seq, ago = int(p.get("seq")), max(0, int(p.get("ago_s", 0) or 0))
    except (TypeError, ValueError):
        return None
    kind = p.get("kind") if p.get("kind") in KINDS else "leave"
    env = p.get("env") if isinstance(p.get("env"), dict) else {}
    env = {k: v for k, v in {"temp": _num(env.get("temp"), -40, 85), "humid": _num(env.get("humid"), 0, 100, 0),
                             "pressure": _num(env.get("pressure"), 300, 1100), "gas": _num(env.get("gas"), 0, 1e8, 0)}.items()
           if v is not None}
    place = p.get("place") if isinstance(p.get("place"), dict) else {}
    place = {k: str(place[k]).lower() for k, _ in LEVELS if re.fullmatch(r"[0-9a-fA-F]{6}", str(place.get(k, "")))}
    sats = _num(p.get("sats"), 0, 99, 0)
    # 時刻: GPS か NTP の時計があれば epoch(秒)。なければ「何秒前」(同じ立ち上がりの間だけ)。どちらもなければ届いた時刻
    at, known = now - timedelta(seconds=min(ago, 30 * 86400)), not p.get("unknown")
    try:
        ep = datetime.fromtimestamp(int(p["epoch"])) if p.get("epoch") else None
    except (TypeError, ValueError, OverflowError, OSError):
        ep = None
    if ep and now - timedelta(days=30) <= ep <= now + timedelta(minutes=5):
        at, known = min(ep, now), True
    return {"seq": seq, "at": _iso(at), "got": _iso(now), "kind": kind, "env": env, "place": place,
            "sats": int(sats) if sats is not None else None, "late": (now - at).total_seconds() >= LATE_SECONDS or not known,
            "known": known}


def receive(report: dict, base: Path | None = None, now: datetime | None = None, via: str = "wifi") -> dict:
    """ボタンの 1 回の連絡(押した分をまとめて)。seq が同じものは 2 度入れない。受け取った seq を返す(ボタンはそこまで消す)"""
    now = now or datetime.now()
    boot = str(report.get("boot", ""))[:16]   # ボタンが立ち上がるたびに変わる印(seq はそのたびに 1 から)
    have = {(p.get("boot"), p.get("seq")) for p in presses(base)}
    got, new = [], []
    for raw in report.get("presses") or []:
        p = _clean(raw, now)
        if p is None:
            continue
        got.append(p["seq"])
        if (boot, p["seq"]) in have:
            continue
        p["boot"] = boot
        p["via"] = via
        new.append(p)
    if new:
        _save(_presses_path(base), (presses(base) + new)[-KEEP:])
    tells = [_pid(p) for p in new if p["kind"] == "tell" and not p["late"]]   # その場で起こす分(外でためた分は、次に起きたときの 1 行へ)
    st = status(base) | ({"at": _iso(now), "fix": bool(report.get("fix")), "queued": len(report.get("presses") or [])}
                         if via == "wifi" else {"ble_at": _iso(now)})
    _save(base_dir(base) / "state" / "button" / "status.json", st)
    return {"ok": got, "new": len(new), "tells": tells}


def from_ble(hex_data: str, base: Path | None = None) -> dict | None:
    """スマホが拾ったボタンの BLE(製造者 0xFFFF の 27 バイト)を、receive の形に。署名が合わなければ None。
    0: 0xB0 | 知らせる 1 | 空気 2 | 場所 4 / 1-2: ボタンの印 / 3-4: 番号 / 5-6: 何秒前 / 7-8: 気温×100 / 9: 湿度 /
    10-11: 気圧×10 / 12-13: ガス÷10 / 14-22: 場所の印 3 つ(3 バイトずつ) / 23-26: HMAC-SHA256(家の鍵, 0-22) の先頭 4"""
    import hashlib
    import hmac
    try:
        b = bytes.fromhex(str(hex_data))
    except ValueError:
        return None
    key = config(base).get("key")
    if len(b) != 27 or b[0] >> 4 != 0xB or not key:
        return None
    if not hmac.compare_digest(hmac.new(str(key).encode(), b[:23], hashlib.sha256).digest()[:4], b[23:]):
        return None
    u16 = lambda i: (b[i] << 8) | b[i + 1]  # noqa: E731
    temp = u16(7) - 65536 if u16(7) >= 32768 else u16(7)
    press = {"seq": u16(3), "kind": "tell" if b[0] & 1 else "leave"}
    if u16(5) == 65535:
        press["unknown"] = True
    else:
        press["ago_s"] = u16(5)
    if b[0] & 2:
        press["env"] = {"temp": temp / 100, "humid": b[9], "pressure": u16(10) / 10, "gas": u16(12) * 10}
    if b[0] & 4:
        press["place"] = {k: b[14 + i * 3:17 + i * 3].hex() for i, (k, _) in enumerate(LEVELS)}
    return {"boot": f"{u16(1):04x}", "presses": [press]}


def status(base: Path | None = None) -> dict:
    return _load(base_dir(base) / "state" / "button" / "status.json", {})


# ---- ぷちへの 1 行 ----
def _told_path(character_id: str, base: Path | None = None) -> Path:
    return base_dir(base) / "characters" / character_id / "state" / "button_told.json"


def _pid(p: dict) -> str:
    return f"{p.get('boot', '')}:{p.get('seq')}"


def _place_text(p: dict, before: list[dict]) -> str:
    if not p.get("place"):
        return "場所の印なし(GPS がまだ空を見つけていない)"
    out = []
    for k, label in LEVELS:
        tok = p["place"].get(k)
        if tok:
            seen = any((q.get("place") or {}).get(k) == tok for q in before)
            out.append(f"{label} {tok}({'前にも' if seen else 'はじめて'})")
    return "場所の印: " + "・".join(out)


def _env_text(env: dict) -> str:
    parts = [f"{env['temp']:g}℃" if "temp" in env else "", f"{env['humid']:g}%" if "humid" in env else "",
             f"{env['pressure']:g}hPa" if "pressure" in env else ""]
    parts = [x for x in parts if x]
    return "まわりの空気 " + " ".join(parts) if parts else ""


def _row(p: dict, before: list[dict], who: str, with_kind: bool = True) -> str:
    at = _parse(p["at"])
    when = at.strftime("%-m/%-d %H:%M") if at else "?"
    act = "長く押した(知らせる: いま知らせたい)" if p["kind"] == "tell" else "押した(おいておく)"
    bits = [f"{when} {who}がぷちボタンを{act}" if with_kind else f"{when}"]
    if p.get("known") is False:
        bits[0] = (f"{who}がぷちボタンを{act}" if with_kind else "") + f"(押した時刻はわからない。{when} に届いた)"
    elif p.get("late"):
        bits.append("あとから届いた")
    if (e := _env_text(p.get("env") or {})):
        bits.append(e)
    bits.append(_place_text(p, before))
    return "。".join(bits)


def press_text(pid: str, base: Path | None = None) -> str:
    """1 回の押しの中身(時刻・空気・場所の印)。その場で起こすときのプロンプト用"""
    allp = presses(base)
    for i, p in enumerate(allp):
        if _pid(p) == pid:
            return _row(p, allp[:i], "", with_kind=False)
    return ""


def mark_told(character_id: str, pids: list[str], base: Path | None = None) -> None:
    told = list(_load(_told_path(character_id, base), []))
    _save(_told_path(character_id, base), (told + [x for x in pids if x not in told])[-KEEP:])


def line(character_id: str, base: Path | None = None, mark: bool = False) -> str:
    """まだ伝えていない押しを 1 行ずつ(新しい LINE_MAX 個まで)。押した人・時刻・空気・場所の印。どうするかはその子が決める"""
    allp = presses(base)
    told = set(_load(_told_path(character_id, base), []))
    fresh = [p for p in allp if _pid(p) not in told]
    if not fresh:
        return ""
    who = config(base).get("owner_name") or "家の人"
    rows = ["(" + _row(p, allp[:allp.index(p)], who) + ")" for p in fresh[-LINE_MAX:]]
    more = len(fresh) - LINE_MAX
    head = f"ぷちボタン: まだ伝えていない押しが {len(fresh)} 回" + (f"(古い {more} 回は省いた)" if more > 0 else "") + "。何をするかは、あなたが決める"
    if mark:
        mark_told(character_id, [_pid(p) for p in fresh], base)
    return head + "\n" + "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ぷちボタン")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("line")
    p.add_argument("--character", required=True)
    p.add_argument("--mark", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "line":
        s = line(a.character, mark=a.mark)
        if s:
            print(s)
    else:
        cfg = config()
        print(json.dumps({"connected": bool(cfg.get("key")), "presses": len(presses()), **status()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
