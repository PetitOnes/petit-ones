#!/usr/bin/env python3
"""家の中の場所(あり部屋:ソファ、寝室:窓際 …)と、ぷちの体がいまどこに置かれているか(人が決める)。

家の設定 PETIT_DATA_DIR/config/spots.json(⚙️ 設定 → 家 → 家の中の場所。git には入れない):

    {"spots": [{"id": "a1b2", "room": "あり部屋", "spot": "ソファ", "devices": ["<SwitchBot の id>", …]}]}

- room: 部屋、spot: その中の場所。devices: その部屋にある SwitchBot の機体(家の空気を「いる部屋」で選ぶため)
- ぷちの体の場所は characters/<id>/state/spot.json {"spot_id", "since", "by"}(ようす の「いる場所」で押す)

使うところ: 📍(体の居場所「家(あり部屋:ソファ)」)、家の空気の 1 行(いる部屋の機体を先に)、ようす のカード。

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
from datetime import datetime
from pathlib import Path

ROOM_MAX = 20
SPOTS_MAX = 40


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


def set_body_spot(base: Path | None, character_id: str, spot_id: str | None, by: str = "", now: datetime | None = None) -> dict | None:
    """その子の体の場所を決める(None で消す)"""
    p = _body_path(base, character_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not spot_id:
        p.unlink(missing_ok=True)
        return None
    if not any(s["id"] == spot_id for s in load(base)):
        raise ValueError("その場所はありません")
    d = {"spot_id": spot_id, "since": (now or datetime.now()).replace(microsecond=0).isoformat(), "by": by}
    p.write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")
    return d


def body_spot(base: Path | None, character_id: str) -> dict | None:
    """その子の体の場所 {"id", "room", "spot", "label", "since", "devices"}。無ければ None"""
    try:
        d = json.loads(_body_path(base, character_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    s = next((s for s in load(base) if s["id"] == d.get("spot_id")), None)
    if not s:
        return None
    return {**s, "label": label(s), "since": d.get("since", "")}


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
        b = body_spot(base, a.character)
        if b:
            print(b["label"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
