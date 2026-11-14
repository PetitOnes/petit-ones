#!/usr/bin/env python3
"""変わったときの一言を、その子が受け取るかどうか(ぷちごとの設定。2026-11-14 ありさん)。

空・家の空気・スマホの部屋は、ぷちたちの希望で「毎回でなく変わったときだけ」渡している。
どれを受け取るかは子ごとに決められる。置き場所は characters/<id>/config/settings.json の "notices":

    {"notices": {"temperature": true, "humidity": true, "pressure": false, "sky": true, "phone": true}}

無いものは受け取る(true)。入口(sky.py line / room_log.py line / phone_place.py line)は設定に関わらずいつもある。

Usage:
    python3 notices.py show <id>            # その子が受け取るもの(JSON)
    python3 notices.py wants <id> <kind>    # 受け取るなら 0、受け取らないなら 1 で終わる(シェルの if 用)
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


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "show":
        print(json.dumps(enabled(sys.argv[2]), ensure_ascii=False))
        return 0
    if len(sys.argv) >= 4 and sys.argv[1] == "wants":
        return 0 if wants(sys.argv[2], sys.argv[3]) else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
