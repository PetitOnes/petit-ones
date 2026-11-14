#!/usr/bin/env python3
"""変わったときの一言を、その子が受け取るかどうか(ぷちごとの設定。2026-11-14 ありさん)。

空・家の空気・スマホの部屋は、ぷちたちの希望で「毎回でなく変わったときだけ」渡している。
どれを受け取るかは子ごとに決められる。置き場所は characters/<id>/config/settings.json の "notices":

    {"notices": {"temperature": true, "humidity": true, "pressure": false, "co2": true, "sky": true, "phone": true}}

無いものは受け取る(true)。入口(sky.py line / room_log.py line / phone_place.py line)は設定に関わらずいつもある。

ぷち自身も変えられる(2026-11-14 ありさん)。settings.json のこの項目だけ書き換え、ほかの設定は触らない。

Usage:
    python3 notices.py show <id>                 # その子が受け取るもの(JSON)
    python3 notices.py set <id> <kind> on|off    # 受け取る・受け取らないを決める(kind: temperature / humidity / pressure / co2 / sky / phone)
    python3 notices.py wants <id> <kind>         # 受け取るなら 0、受け取らないなら 1 で終わる(シェルの if 用)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

KINDS = {
    "temperature": "気温が 2℃ 以上動いたとき",
    "humidity": "湿度が 10% 以上動いたとき",
    "pressure": "気圧が 3 hPa 以上動いたとき",
    "co2": "CO2 が 1000 ppm を超えたとき(戻ったときも)",
    "sky": "空(満月・新月・二十四節気の境目の日)",
    "phone": "家の人のスマホの部屋が変わったとき",
}


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def enabled(character_id: str, base: Path | None = None) -> dict[str, bool]:
    """種類ごとに、受け取るか。設定に無いものは受け取る"""
    try:
        d = json.loads(((base or data_dir()) / "characters" / character_id / "config" / "settings.json").read_text(encoding="utf-8"))
        raw = d.get("notices") if isinstance(d, dict) and isinstance(d.get("notices"), dict) else {}
    except (OSError, json.JSONDecodeError):
        raw = {}
    return {k: (bool(raw[k]) if k in raw else True) for k in KINDS}


def wants(character_id: str, kind: str, base: Path | None = None) -> bool:
    return enabled(character_id, base).get(kind, True)


def clean(raw: object) -> dict[str, bool]:
    """画面から来たものを、知っている種類だけ bool に"""
    return {k: bool(v) for k, v in (raw or {}).items() if k in KINDS} if isinstance(raw, dict) else {}


def set_kind(character_id: str, kind: str, on: bool, base: Path | None = None) -> dict[str, bool]:
    """その種類だけ書き換える(settings.json のほかの項目は触らない)。知らない種類は ValueError"""
    if kind not in KINDS:
        raise ValueError(f"知らない種類: {kind}(使えるのは {', '.join(KINDS)})")
    p = (base or data_dir()) / "characters" / character_id / "config" / "settings.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    cur = d.get("notices") if isinstance(d.get("notices"), dict) else {}
    d["notices"] = {**cur, kind: bool(on)}
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return enabled(character_id, base)


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "show":
        print(json.dumps(enabled(sys.argv[2]), ensure_ascii=False))
        return 0
    if len(sys.argv) >= 5 and sys.argv[1] == "set":
        on = sys.argv[4].lower()
        if on not in ("on", "off"):
            print("on か off で", file=sys.stderr)
            return 2
        try:
            now = set_kind(sys.argv[2], sys.argv[3], on == "on")
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"{KINDS[sys.argv[3]]} の一言を、{'受け取る' if on == 'on' else '受け取らない'}ことにした。いま: " + "、".join(f"{k}={'on' if v else 'off'}" for k, v in now.items()))
        return 0
    if len(sys.argv) >= 4 and sys.argv[1] == "wants":
        return 0 if wants(sys.argv[2], sys.argv[3]) else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
