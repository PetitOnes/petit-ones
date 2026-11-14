#!/usr/bin/env python3
"""家の中の場所(あり部屋:ソファ、寝室:窓際 …)と、ぷちの体がいまどこに置かれているか(人が決める)。

家の設定 PETIT_DATA_DIR/config/spots.json(⚙️ 設定 → 家 → 家の中の場所。git には入れない):

    {"spots": [{"id": "a1b2", "room": "あり部屋", "spot": "ソファ", "devices": ["<SwitchBot の id>", …]}]}

- room: 部屋、spot: その中の場所。devices: その部屋にある SwitchBot の機体(家の空気を「いる部屋」で選ぶため)
- ぷちの体の場所は characters/<id>/state/spot.json {"spot_id", "since", "by"}(ようす の「いる場所」で押す)

使うところ: 📍(体の居場所「家(あり部屋:ソファ)」)、家の空気の 1 行(いる部屋の機体を先に)、ようす のカード。

「かも」(電波からの見立て。任意): 体が返すまわりの Wi-Fi の強さ(/wifi_near。体験デーモンが
characters/<id>/state/wifi_near.json に残す)が、家の設定 config/spot_guess.json の決まりに合えば、
人が押していなくても「あり部屋:ソファかも」と出す。目印(ルーター・発信機)のすぐそばの場所にだけ決まりを書く。

    {"<id>": {"ch": 13, "every_s": 60,
              "rules": [{"spot_id": "<場所の id>", "min": {"now": -38}},
                        {"spot_id": "<場所の id>", "min": {"<発信機の名前>": -41}, "max": {"now": -50}}]}}

- ch / every_s: 体に探してもらうチャンネル(無ければ全部。体が 2〜3 秒止まる)と、何秒ごとに聞くか
- rules: 上から順に、はじめに合った場所。now = いまつながっている Wi-Fi、ほかは聞こえた Wi-Fi の名前。
  min は「これ以上強い」、max は「これ以下」。比べるのは、ここ数回のまんなかの値
- 人が押したあと、見立てが変わらないあいだは、押した場所のまま(人の言うことが先)

Usage:
    python3 spots.py list
    python3 spots.py where --character <id>     # その子の体の場所(無ければ何も出さない)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOM_MAX = 20
SPOTS_MAX = 40
GUESS_FRESH_S = 300   # これより古い電波の記録は使わない
GUESS_SAMPLES = 3     # まんなかを取る回数
GUESS_SILENT = -100   # 聞こえなかった目印の強さ


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def path(base: Path | None = None) -> Path:
    return (base or data_dir()) / "config" / "spots.json"


def clean(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("場所の形がおかしい")
    room = str(raw.get("room", "")).strip()
    spot = str(raw.get("spot", "")).strip()
    if not room:
        raise ValueError("部屋を入れてください")
    if len(room) > ROOM_MAX or len(spot) > ROOM_MAX:
        raise ValueError(f"部屋・場所は {ROOM_MAX} 字まで")
    devices = [str(d) for d in (raw.get("devices") or []) if isinstance(d, str) and d.strip()][:20]
    return {"id": str(raw.get("id") or uuid.uuid4().hex[:8]), "room": room, "spot": spot, "devices": devices}


def load(base: Path | None = None) -> list[dict]:
    try:
        d = json.loads(path(base).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for it in d.get("spots", []) if isinstance(d, dict) else []:
        try:
            out.append(clean(it))
        except ValueError:
            continue
    return out


def save(spots: list[dict], base: Path | None = None) -> list[dict]:
    items = [clean(s) for s in spots][:SPOTS_MAX]
    p = path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"spots": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return items


def label(s: dict) -> str:
    return f"{s['room']}:{s['spot']}" if s.get("spot") else s["room"]


def _body_path(base: Path | None, character_id: str) -> Path:
    return (base or data_dir()) / "characters" / character_id / "state" / "spot.json"


def _read_body(base: Path | None, character_id: str) -> dict:
    try:
        d = json.loads(_body_path(base, character_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return d if isinstance(d, dict) else {}


def set_body_spot(base: Path | None, character_id: str, spot_id: str | None, by: str = "", now: datetime | None = None) -> dict | None:
    """その子の体の場所を決める(None で消す)。そのときの電波の見立ても一緒に残す(あとで見立てが変わったかを知るため)"""
    p = _body_path(base, character_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not spot_id:
        p.unlink(missing_ok=True)
        return None
    if not any(s["id"] == spot_id for s in load(base)):
        raise ValueError("その場所はありません")
    now = now or datetime.now()
    d = {"spot_id": spot_id, "since": now.replace(microsecond=0).isoformat(), "by": by}
    known, gid = guess(base, character_id, now)
    if known:
        d["guess_then"] = gid
    p.write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")
    return d


def body_spot(base: Path | None, character_id: str) -> dict | None:
    """人が押した、その子の体の場所 {"id", "room", "spot", "label", "since", "devices"}。無ければ None"""
    d = _read_body(base, character_id)
    s = next((s for s in load(base) if s["id"] == d.get("spot_id")), None)
    if not s:
        return None
    return {**s, "label": label(s), "since": d.get("since", "")}


def guess_rules(base: Path | None, character_id: str) -> list[dict]:
    try:
        d = json.loads(((base or data_dir()) / "config" / "spot_guess.json").read_text(encoding="utf-8"))
        rules = d[character_id]["rules"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return []
    return [r for r in rules if isinstance(r, dict) and r.get("spot_id")] if isinstance(rules, list) else []


def _wifi_levels(base: Path | None, character_id: str, now: datetime) -> dict[str, float] | None:
    """ここ数回の電波の強さの、目印ごとのまんなか。新しい記録が 2 回分より少なければ None"""
    try:
        d = json.loads(((base or data_dir()) / "characters" / character_id / "state" / "wifi_near.json").read_text(encoding="utf-8"))
        samples = [x for x in d["samples"] if now - datetime.fromisoformat(x["ts"]) <= timedelta(seconds=GUESS_FRESH_S)]
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    samples = samples[-GUESS_SAMPLES:]
    if len(samples) < 2:
        return None
    names = {"now"} | {n for x in samples for n in (x.get("marks") or {})}
    out = {}
    for n in names:
        vals = sorted((x.get("now") if n == "now" else (x.get("marks") or {}).get(n)) or GUESS_SILENT for x in samples)
        out[n] = vals[len(vals) // 2]
    return out


def _fits(rule: dict, levels: dict[str, float]) -> bool:
    try:
        return (all(levels.get(k, GUESS_SILENT) >= float(v) for k, v in (rule.get("min") or {}).items())
                and all(levels.get(k, GUESS_SILENT) <= float(v) for k, v in (rule.get("max") or {}).items()))
    except (TypeError, ValueError):
        return False


def guess(base: Path | None, character_id: str, now: datetime | None = None) -> tuple[bool, str | None]:
    """電波からの見立て (分かるか, 場所の id)。決まりが無い・記録が古いなら (False, None)。どの決まりにも合わなければ (True, None)"""
    rules = guess_rules(base, character_id)
    if not rules:
        return False, None
    levels = _wifi_levels(base, character_id, now or datetime.now())
    if levels is None:
        return False, None
    ids = {s["id"] for s in load(base)}
    return True, next((r["spot_id"] for r in rules if r["spot_id"] in ids and _fits(r, levels)), None)


def effective(base: Path | None, character_id: str, now: datetime | None = None) -> dict | None:
    """その子の体の場所。body_spot と同じ形に "guess"(電波からの見立てなら True)が付く。分からなければ None。

    - 見立てが分からない(決まりが無い・記録が古い): 人が押した場所
    - 見立てがあり、押した場所と違う: 見立て(かも)。ただし、押したときからその見立てだった(人が言い直した)なら、押した場所
    - どの決まりにも合わないのに、押した場所は決まりのある場所: 押したあとに動いた → 分からない
    """
    pressed = body_spot(base, character_id)
    known, gid = guess(base, character_id, now)
    if not known:
        return {**pressed, "guess": False} if pressed else None
    then = _read_body(base, character_id).get("guess_then") if pressed else None
    if gid and not (pressed and gid in (pressed["id"], then)):
        s = next(s for s in load(base) if s["id"] == gid)
        return {**s, "label": label(s), "since": "", "guess": True}
    if gid is None and pressed and then is not None and any(r["spot_id"] == pressed["id"] for r in guess_rules(base, character_id)):
        return None
    return {**pressed, "guess": False} if pressed else None


def room_devices(base: Path | None, room: str) -> list[str]:
    out: list[str] = []
    for s in load(base):
        if s["room"] == room:
            out += [d for d in s["devices"] if d not in out]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("where")
    p.add_argument("--character", required=True)
    a = ap.parse_args()
    base = data_dir()
    if a.cmd == "list":
        for s in load(base):
            print(f"{label(s)}  [id {s['id']}]" + (f"  機体: {len(s['devices'])}" if s["devices"] else ""))
    else:
        b = effective(base, a.character)
        if b:
            print(b["label"] + ("かも" if b["guess"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
