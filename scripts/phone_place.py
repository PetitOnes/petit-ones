#!/usr/bin/env python3
"""スマホの居場所: 家の印(SwitchBot の機体が出している BLE)をスマホが聞いて、どの部屋にいるかを決める。

SwitchBot の機体(ハブ 2・温湿度計・人感・電気)は、機体 ID そのままの MAC で BLE をずっと出している。
部屋ごとにどの機体があるかは config/spots.json(家の中の場所)に書いてある。
スマホ(Android の Garmin BLE Bridge アプリ)が 30 秒ごとに、見えた機体と電波の強さ(RSSI)を
ダッシュボードの POST /api/beacons/report に送ってくる。ここはそれを部屋に直して覚える(2026-11-14 ありさん)。

設定 PETIT_DATA_DIR/config/beacons.json(無ければ何もしない):

    {"phones": {"arisan": {"key": "<長いランダムな文字列>", "label": "ありさんのスマホ"}},
     "hysteresis_db": 6, "fresh_s": 240, "window": 3, "min_rssi": -95}

- phones: ダッシュボードのユーザー名ごとに、スマホが名乗る鍵(X-Petit-Key)。鍵は `phone_place.py key <ユーザー名>` で作る
- hysteresis_db: いまの部屋より、これだけ強い部屋が出たときだけ移る(部屋の境目でパタパタしないように)
- fresh_s: 最後の報告がこれより古ければ「分からない」
- window: 直近いくつの報告のまんなか(中央値)で決めるか
- min_rssi: これより弱い電波は「見えていない」と同じ

覚え書き PETIT_DATA_DIR/state/phone_place.json:

    {"arisan": {"room": "あり部屋", "since": "...", "at": "...", "levels": {"あり部屋": -58, "寝室": -81},
                "history": [{"at": "...", "rooms": {"あり部屋": -60}}]}}

- room: いまいる部屋(どの印も見えなければ null)。since はその部屋になった時刻、at は最後の報告
- 部屋は分かるが、ソファか机かまでは電波では分からない

ぷちに渡す行(scripts/whereabouts.py が人の行のあとに足す):

    ありさんのスマホ: 家(あり部屋)
    ありさんのスマホ: 家の印が見えない(お外か、印の無い部屋)

Usage:
    python3 phone_place.py key <ユーザー名> [--label "ありさんのスマホ"]   # 鍵を作って設定に書く(鍵は画面に出さない)
    python3 phone_place.py show                                          # いまの覚え書き
    python3 phone_place.py line                                          # ぷちに渡す行
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULTS = {"hysteresis_db": 6, "fresh_s": 240, "window": 3, "min_rssi": -95}
SILENT = -100          # 見えていない部屋の電波の強さ、として扱う値
INTERVAL_S = 30        # スマホが報告する間隔(アプリに伝える)
HISTORY_MAX = 10


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def config_path(base: Path | None = None) -> Path:
    return (base or data_dir()) / "config" / "beacons.json"


def state_path(base: Path | None = None) -> Path:
    return (base or data_dir()) / "state" / "phone_place.json"


def config(base: Path | None = None) -> dict:
    try:
        raw = json.loads(config_path(base).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    out = {**DEFAULTS, **{k: v for k, v in raw.items() if k in DEFAULTS and isinstance(v, (int, float))}}
    phones = raw.get("phones") if isinstance(raw.get("phones"), dict) else {}
    out["phones"] = {u: p for u, p in phones.items() if isinstance(p, dict) and p.get("key")}
    return out


def person_for_key(key: str | None, base: Path | None = None) -> str | None:
    """名乗った鍵がだれのスマホか。合わなければ None"""
    if not key:
        return None
    for user, p in config(base)["phones"].items():
        if secrets.compare_digest(str(p["key"]), key):
            return user
    return None


def make_key(user: str, label: str = "", base: Path | None = None) -> None:
    """鍵を作って設定に書く(前の鍵は捨てる)。鍵そのものは返さない"""
    p = config_path(base)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    phones = raw.setdefault("phones", {})
    phones[user] = {"key": secrets.token_urlsafe(32), "label": label or phones.get(user, {}).get("label") or f"{user} のスマホ"}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass


def norm_mac(mac: str) -> str:
    return "".join(c for c in str(mac).upper() if c in "0123456789ABCDEF")


def mac_rooms(base: Path | None = None) -> dict[str, str]:
    """印(機体の MAC)→ 部屋。家の中の場所(spots.json)から"""
    import spots
    out: dict[str, str] = {}
    for s in spots.load(base):
        for d in s.get("devices") or []:
            out.setdefault(norm_mac(d), s["room"])
    return out


def macs(base: Path | None = None) -> list[str]:
    """スマホに「これを聞いて」と渡す MAC の一覧(12 桁、大文字)"""
    return sorted(mac_rooms(base))


def rooms_from_seen(seen: dict, base: Path | None = None, min_rssi: float = DEFAULTS["min_rssi"]) -> dict[str, int]:
    """見えた機体と強さ → 部屋ごとのいちばん強い値"""
    rooms = mac_rooms(base)
    out: dict[str, int] = {}
    for mac, rssi in (seen or {}).items():
        room = rooms.get(norm_mac(mac))
        try:
            v = int(rssi)
        except (TypeError, ValueError):
            continue
        if room and v >= min_rssi:
            out[room] = max(out.get(room, SILENT), v)
    return out


def _load(base: Path | None) -> dict:
    try:
        d = json.loads(state_path(base).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(base: Path | None, d: dict) -> None:
    p = state_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)


def _median_levels(history: list[dict]) -> dict[str, int]:
    names = {r for h in history for r in (h.get("rooms") or {})}
    out = {}
    for n in names:
        vals = sorted((h.get("rooms") or {}).get(n, SILENT) for h in history)
        out[n] = vals[len(vals) // 2]
    return out


def decide(cur_room: str | None, levels: dict[str, int], hysteresis_db: float) -> str | None:
    """いまの部屋と、部屋ごとの強さから、次の部屋。見える部屋が無ければ None"""
    levels = {r: v for r, v in levels.items() if v > SILENT}   # まんなかが「見えていない」の部屋は候補にしない(引き分けで決めてしまわない)
    if not levels:
        return None
    best = max(levels, key=lambda r: levels[r])
    if cur_room and cur_room in levels and best != cur_room and levels[best] - levels[cur_room] < hysteresis_db:
        return cur_room   # いまの部屋とほとんど差が無いなら、動かない
    return best


def report(user: str, seen: dict, base: Path | None = None, now: datetime | None = None) -> dict:
    """スマホからの 1 回の報告を取り込み、その人の覚え書きを返す"""
    now = now or datetime.now()
    cfg = config(base)
    stamp = now.replace(microsecond=0).isoformat()
    d = _load(base)
    cur = d.get(user) if isinstance(d.get(user), dict) else {}
    history = [h for h in (cur.get("history") or []) if isinstance(h, dict)]
    # 古い報告(fresh_s より前)は、まんなかを取る相手にしない(帰ってきた直後に、出かける前の部屋が残らないように)
    history = [h for h in history if _dt(h.get("at")) and now - _dt(h.get("at")) <= timedelta(seconds=cfg["fresh_s"])]
    history.append({"at": stamp, "rooms": rooms_from_seen(seen, base, cfg["min_rssi"])})
    history = history[-HISTORY_MAX:]
    levels = _median_levels(history[-int(cfg["window"]):])
    room = decide(cur.get("room"), levels, cfg["hysteresis_db"])
    since = cur.get("since") if room == cur.get("room") and cur.get("since") else stamp
    d[user] = {"room": room, "since": since, "at": stamp, "levels": levels, "history": history}
    _save(base, d)
    return d[user]


def _dt(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def where(user: str, base: Path | None = None, now: datetime | None = None) -> dict | None:
    """その人のスマホの居場所 {"room", "since", "at", "label"}。報告が古い・無いなら None"""
    now = now or datetime.now()
    cur = _load(base).get(user)
    at = _dt(cur.get("at")) if isinstance(cur, dict) else None
    if at is None or now - at > timedelta(seconds=config(base)["fresh_s"]):
        return None
    label = (config(base)["phones"].get(user) or {}).get("label") or f"{user} のスマホ"
    return {"room": cur.get("room"), "since": cur.get("since") or "", "at": cur.get("at"), "label": label}


def words(w: dict) -> str:
    return f"家({w['room']})" if w.get("room") else "家の印が見えない(お外か、印の無い部屋)"


def lines(base: Path | None = None, label=lambda u: u, now: datetime | None = None) -> list[str]:
    """ぷちに渡す行。「ありさんのスマホ: 家(あり部屋)」"""
    out = []
    for user in config(base)["phones"]:
        w = where(user, base, now)
        if w:
            out.append(f"{label(user)}のスマホ: {words(w)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("key", help="鍵を作って設定に書く")
    k.add_argument("user")
    k.add_argument("--label", default="")
    sub.add_parser("show")
    sub.add_parser("line")
    a = ap.parse_args()
    if a.cmd == "key":
        make_key(a.user, a.label)
        print(f"{a.user} の鍵を {config_path()} に書いた(鍵は表示しない)")
    elif a.cmd == "show":
        print(json.dumps(_load(None), ensure_ascii=False, indent=1))
    else:
        print("\n".join(lines()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
