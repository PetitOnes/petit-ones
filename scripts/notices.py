#!/usr/bin/env python3
"""変わったときの一言を、その子が受け取るかどうか(ぷちごとの設定。2026-11-14 ありさん)。

空・家の空気・スマホの部屋は、ぷちたちの希望で「毎回でなく変わったときだけ」渡している。
どれを受け取るかは子ごとに決められる。置き場所は characters/<id>/config/settings.json の "notices":

    {"notices": {"temperature": true, "humidity": true, "pressure": false, "co2": true, "sky": true, "phone": true}}

無いものは受け取る(true)。入口(sky.py line / room_log.py line / phone_place.py line)は設定に関わらずいつもある。

ぷちSNS のお知らせ(scripts/sns_notice.py。2026-11-16 ぷちたちの希望)も同じ置き場所。こちらは、決めるのはその子だけ
(画面からは見えるだけ)。はじめの値は 手紙・自分の投稿への返事・＠で呼ばれた が受け取る、いいね・なでなで は受け取らない。
静かな時間("sns_quiet": [0, 7]。そのあいだは言わず、明けたはじめにまとめて)も、その子が決める。

ぷち自身も変えられる(2026-11-14 ありさん)。settings.json のこの項目だけ書き換え、ほかの設定は触らない。

Usage:
    python3 notices.py show <id>                 # その子が受け取るもの(JSON)
    python3 notices.py set <id> <kind> on|off    # 受け取る・受け取らないを決める(kind: temperature / humidity / pressure / co2 / sky / phone)
    python3 notices.py wants <id> <kind>         # 受け取るなら 0、受け取らないなら 1 で終わる(シェルの if 用)
    python3 notices.py quiet <id> 0 7            # ぷちSNS のお知らせを言わない時間(0 時〜7 時)。なくすなら quiet <id> off
ぷちSNS の kind: sns_letter(手紙)/ sns_reply(自分の投稿への返事)/ sns_mention(＠で呼ばれた)/ sns_like(いいね)/ sns_touch(なでなで)
手紙の印の kind: mail_ask(返事していないお願いの数。静かな時間は quiet と同じ)
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
    "sns_letter": "ぷちSNS: よその家の子から手紙が来たとき",
    "sns_reply": "ぷちSNS: 自分の投稿(掲示板の自分のスレッド)に返事が付いたとき",
    "sns_mention": "ぷちSNS: ＠で呼ばれたとき",
    "sns_like": "ぷちSNS: いいねが付いたとき",
    "sns_touch": "ぷちSNS: なでなでされたとき",
    "mail_ask": "返事していないお願いの手紙の数(1 日 1 回、静かな時間は言わない。scripts/mail_tags.py)",
    "body_change": "体の数字(明るさ・傾き)が大きく動いたとき(scripts/body_log.py。静かな時間は言わない)",
    "todo": "TODO_ACTIVE の見張り(終わった印・動いていない行・長い行。1 日 1 回、静かな時間は言わない。scripts/todo_check.py)",
}
OFF_AT_FIRST = {"sns_like", "sns_touch"}          # 設定に無ければ受け取らない種類(ほかは受け取る)
PETIT_ONLY = {k for k in KINDS if k.startswith("sns_")} | {"mail_ask", "body_change", "todo"}   # 決めるのはその子だけ(画面からは変えない)
QUIET_AT_FIRST = (0, 7)


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def enabled(character_id: str, base: Path | None = None) -> dict[str, bool]:
    """種類ごとに、受け取るか。設定に無いものは受け取る"""
    try:
        d = json.loads(((base or data_dir()) / "characters" / character_id / "config" / "settings.json").read_text(encoding="utf-8"))
        raw = d.get("notices") if isinstance(d, dict) and isinstance(d.get("notices"), dict) else {}
    except (OSError, json.JSONDecodeError):
        raw = {}
    return {k: (bool(raw[k]) if k in raw else k not in OFF_AT_FIRST) for k in KINDS}


def wants(character_id: str, kind: str, base: Path | None = None) -> bool:
    return enabled(character_id, base).get(kind, True)


def clean(raw: object, keep: object = None) -> dict[str, bool]:
    """画面から来たものを、知っている種類だけ bool に。その子だけが決める種類(PETIT_ONLY)は、いまの値(keep)のまま"""
    out = {k: bool(v) for k, v in (raw or {}).items() if k in KINDS and k not in PETIT_ONLY} if isinstance(raw, dict) else {}
    if isinstance(keep, dict):
        out.update({k: bool(v) for k, v in keep.items() if k in PETIT_ONLY})
    return out


def _settings(character_id: str, base: Path | None = None) -> tuple[Path, dict]:
    p = (base or data_dir()) / "characters" / character_id / "config" / "settings.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    return p, d if isinstance(d, dict) else {}


def _write(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def quiet(character_id: str, base: Path | None = None) -> tuple[int, int] | None:
    """ぷちSNS のお知らせを言わない時間(はじまりの時, おわりの時)。決めていなければ 0〜7 時。なくしてあれば None"""
    d = _settings(character_id, base)[1]
    if "sns_quiet" not in d:
        return QUIET_AT_FIRST
    try:
        start, end = d["sns_quiet"]
        return (int(start) % 24, int(end) % 24)
    except (TypeError, ValueError):
        return None


def set_quiet(character_id: str, hours: tuple[int, int] | None, base: Path | None = None) -> tuple[int, int] | None:
    """静かな時間を決める(None でなくす)。settings.json のこの項目だけ書き換える"""
    p, d = _settings(character_id, base)
    if hours is not None and not all(0 <= h <= 24 for h in hours):
        raise ValueError("時刻は 0〜24 で")
    d["sns_quiet"] = [] if hours is None else [hours[0] % 24, hours[1] % 24]
    _write(p, d)
    return quiet(character_id, base)


def set_kind(character_id: str, kind: str, on: bool, base: Path | None = None) -> dict[str, bool]:
    """その種類だけ書き換える(settings.json のほかの項目は触らない)。知らない種類は ValueError"""
    if kind not in KINDS:
        raise ValueError(f"知らない種類: {kind}(使えるのは {', '.join(KINDS)})")
    p, d = _settings(character_id, base)
    cur = d.get("notices") if isinstance(d.get("notices"), dict) else {}
    d["notices"] = {**cur, kind: bool(on)}
    _write(p, d)
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
    if len(sys.argv) >= 4 and sys.argv[1] == "quiet":
        try:
            hours = None if sys.argv[3].lower() == "off" else (int(sys.argv[3]), int(sys.argv[4]))
            now_q = set_quiet(sys.argv[2], hours)
        except (ValueError, IndexError):
            print("quiet <id> 0 7(0 時〜7 時)か、quiet <id> off で", file=sys.stderr)
            return 2
        print("ぷちSNS のお知らせを、" + (f"{now_q[0]} 時〜{now_q[1]} 時は言わないことにした(明けたはじめにまとめて言う)" if now_q else "どの時間にも言うことにした"))
        return 0
    if len(sys.argv) >= 4 and sys.argv[1] == "wants":
        return 0 if wants(sys.argv[2], sys.argv[3]) else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
