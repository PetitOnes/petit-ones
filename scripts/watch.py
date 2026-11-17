#!/usr/bin/env python3
"""ぷち時計(家の表示機。M5Stack StopWatch)への通知(2026-11-17、ありさんと 3 人で決めた)。

決まり(3 人の回覧板の返事と、ありさんの答えから):
- 通知は「いま」のひとこと。残したいことは手紙。1 人 1 日 3 回まで、3 行・40 字まで
- 送れるのは、夜(0:00〜7:00)の外で、家の人が時計を持っているときだけ。持っているときだけ、自律行動のプロンプトに 1 行出す
- 持っているか = 時計から 10 分以内に連絡があり、15 分以内に動いていて、充電中でも伏せてもいない
- 家の人が見たかは、ぷちに伝えない。家の人が時計で「見たよ」を返したときだけ、次の自律行動で 1 行伝える
- ほかの子の通知は見えない(この道具は、自分が送った分しか出さない)
- 通知は家の人がいつでも切れる(時計の上でも、ダッシュボードの 設定 → 家 でも。同じ 1 つの値)

置き場所(PETIT_DATA_DIR の中。git には入れない):
- config/watch.json   鍵・持ち主・通知のオン/オフ・数字(回数・字数・夜・分)
- state/watch/status.json   時計の最後のようす
- state/watch/notices.json  送られた通知(古いものから消す)
- characters/<id>/state/watch_told.json  「見たよ」を伝えた分

Usage:
    python3 watch.py line --character <id>        # 送れるときだけ、プロンプトの 1 行
    python3 watch.py send --character <id> "ひとこと"
    python3 watch.py notice --character <id> [--mark]   # 「見たよ」が返ってきた分
    python3 watch.py status
    python3 watch.py make-key [--owner <user> --owner-name <呼び名>]   # 鍵を作り直す(鍵は出さない)
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path

DEFAULTS = {"notify": True, "per_day": 3, "max_chars": 40, "max_lines": 3,
            "quiet": [0, 7], "held_minutes": 15, "seen_minutes": 10, "owner_name": "家の人"}
KEEP = 300   # notices.json に残す数


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


def config_path(base: Path | None = None) -> Path:
    return base_dir(base) / "config" / "watch.json"


def config(base: Path | None = None) -> dict:
    raw = _load(config_path(base), {})
    return {**DEFAULTS, **(raw if isinstance(raw, dict) else {})}


def save_config(changes: dict, base: Path | None = None) -> dict:
    raw = _load(config_path(base), {})
    raw = {**(raw if isinstance(raw, dict) else {}), **changes}
    _save(config_path(base), raw, private=True)
    return config(base)


def make_key(base: Path | None = None, owner: str | None = None, owner_name: str | None = None) -> str:
    """鍵を作り直す(前の鍵は使えなくなる)。返した鍵は、画面に出すときだけ使う"""
    key = secrets.token_urlsafe(24)
    ch = {"key": key}
    if owner:
        ch["owner"] = owner
    if owner_name:
        ch["owner_name"] = owner_name
    save_config(ch, base)
    return key


PAIR_MINUTES = 10


def make_pair_code(base: Path | None = None, now: datetime | None = None) -> dict:
    """時計をつなぐための 6 桁の番号(10 分だけ)。時計が初めて連絡してきたとき、この番号と引き換えに長い鍵を渡す"""
    now = now or datetime.now()
    if not config(base).get("key"):
        make_key(base)
    code = f"{secrets.randbelow(1_000_000):06d}"
    until = now + timedelta(minutes=PAIR_MINUTES)
    save_config({"pair": {"code": code, "until": _iso(until)}}, base)
    return {"code": code, "until": _iso(until)}


def redeem_pair(code: str | None, base: Path | None = None, now: datetime | None = None) -> str | None:
    """番号が合えば、長い鍵を返す(番号は 1 回で消える)。合わなければ None"""
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


def _state_dir(base: Path | None = None) -> Path:
    return base_dir(base) / "state" / "watch"


def status(base: Path | None = None) -> dict:
    return _load(_state_dir(base) / "status.json", {})


def _notices(base: Path | None = None) -> list[dict]:
    d = _load(_state_dir(base) / "notices.json", [])
    return d if isinstance(d, list) else []


def _save_notices(items: list[dict], base: Path | None = None) -> None:
    _save(_state_dir(base) / "notices.json", items[-KEEP:])


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _parse(s) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def is_quiet(cfg: dict, now: datetime) -> bool:
    q = cfg.get("quiet")
    if not q:
        return False
    a, b = int(q[0]), int(q[1])
    h = now.hour
    return a <= h < b if a <= b else (h >= a or h < b)


def held(base: Path | None = None, now: datetime | None = None) -> bool:
    """家の人が時計をいま持っているか"""
    now = now or datetime.now()
    cfg, st = config(base), status(base)
    at, moved = _parse(st.get("at")), _parse(st.get("moved_at"))
    if not at or not moved or st.get("charging") or st.get("face_down"):
        return False
    return (now - at <= timedelta(minutes=cfg["seen_minutes"])
            and now - moved <= timedelta(minutes=cfg["held_minutes"]))


def sent_today(character_id: str, base: Path | None = None, now: datetime | None = None) -> int:
    day = (now or datetime.now()).date().isoformat()
    return sum(1 for n in _notices(base) if n.get("from") == character_id and str(n.get("at", "")).startswith(day))


def can_send(character_id: str, base: Path | None = None, now: datetime | None = None) -> tuple[bool, str, int]:
    """(送れるか, 送れないわけ, きょうのあと何回)"""
    now = now or datetime.now()
    cfg = config(base)
    left = max(0, int(cfg["per_day"]) - sent_today(character_id, base, now))
    if not cfg.get("key"):
        return False, "この家には、まだ時計がつながっていないよ。", left
    if not cfg.get("notify"):
        return False, "いまは時計の通知を切ってあるよ。残したいことなら手紙にしてね。", left
    if is_quiet(cfg, now):
        return False, "夜は時計に通知を送らない決まりだよ。残したいことなら手紙にしてね。", left
    if not held(base, now):
        return False, "いまは時計が手元にないみたい。残したいことなら手紙にしてね。", left
    if left <= 0:
        return False, f"時計への通知は、きょうはもう {cfg['per_day']} 回送ったよ。続きは手紙にしてね。", left
    return True, "", left


def check_text(text: str, cfg: dict) -> str:
    """直したほうがいいところ(無ければ空)"""
    t = text.strip()
    if not t:
        return "ひとことが空だよ。"
    if len(t.replace("\n", "")) > int(cfg["max_chars"]):
        return f"{cfg['max_chars']} 字までにしてね(いま {len(t.replace(chr(10), ''))} 字)。"
    if t.count("\n") + 1 > int(cfg["max_lines"]):
        return f"{cfg['max_lines']} 行までにしてね。"
    return ""


def send(character_id: str, text: str, base: Path | None = None, now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now()
    ok, why, left = can_send(character_id, base, now)
    if not ok:
        return False, why
    bad = check_text(text, config(base))
    if bad:
        return False, bad
    items = _notices(base)
    nid = (max((int(n.get("id", 0)) for n in items), default=0) + 1)
    items.append({"id": nid, "from": character_id, "text": text.strip(), "at": _iso(now)})
    _save_notices(items, base)
    return True, f"時計に送ったよ(5 分くらいで届く)。きょうはあと {left - 1} 回。見たかどうかは伝わらないよ。"


def line(character_id: str, base: Path | None = None, now: datetime | None = None, project: str | None = None) -> str:
    """送れるときだけ、自律行動のプロンプトに出す 1 行。送れないときは空(ないことも言わない)"""
    ok, _, left = can_send(character_id, base, now)
    if not ok:
        return ""
    cfg = config(base)
    proj = project or str(Path(os.path.abspath(__file__)).parent.parent)
    return (f"⌚ {cfg['owner_name']}の時計がいま手元にある。「いま」のことをひとことだけ、時計に通知で送れる"
            f"({cfg['max_lines']} 行・{cfg['max_chars']} 字まで。きょうはあと {left} 回。残したいことは手紙で。送らなくていい): "
            f"python3 {proj}/scripts/watch.py send --character {character_id} \"ひとこと\"")


# ---- 時計から(ダッシュボードの /api/watch/sync) ----

def sync(report: dict, base: Path | None = None, now: datetime | None = None) -> dict:
    """時計の 1 回の連絡: ようすを覚え、「見たよ」を受け取り、通知のオン/オフの切り替えを受け、まだ渡していない通知を返す。

    report: {"after": 最後に受け取った通知の id, "still_s": 動いていない秒, "charging", "face_down", "battery",
             "mita": [「見たよ」を押した通知の id], "notify_set": 時計で切り替えたときだけ true/false}
    """
    now = now or datetime.now()
    still = max(0, int(report.get("still_s") or 0))
    _save(_state_dir(base) / "status.json", {
        "at": _iso(now), "moved_at": _iso(now - timedelta(seconds=still)),
        "charging": bool(report.get("charging")), "face_down": bool(report.get("face_down")),
        "battery": report.get("battery")})
    if isinstance(report.get("notify_set"), bool):
        save_config({"notify": report["notify_set"]}, base)
    items = _notices(base)
    mita = {int(i) for i in report.get("mita") or [] if str(i).isdigit()}
    if mita:
        for n in items:
            if n.get("id") in mita and not n.get("mita_at"):
                n["mita_at"] = _iso(now)
        _save_notices(items, base)
    after = int(report.get("after") or 0)
    last = max((int(n.get("id", 0)) for n in items), default=0)
    # 時計は last_id を覚え直す(家の側が作り直されて番号が戻っても、次から受け取れる)
    out = [{"id": n["id"], "from": n["from"], "text": n["text"], "at": n["at"]} for n in items if int(n.get("id", 0)) > after]
    cfg = config(base)
    return {"notices": out[-5:], "last_id": last, "notify": bool(cfg.get("notify")), "now": int(now.timestamp())}


# ---- 「見たよ」を、送った子に伝える ----

def _told_path(character_id: str, base: Path | None = None) -> Path:
    return base_dir(base) / "characters" / character_id / "state" / "watch_told.json"


def notice(character_id: str, base: Path | None = None, mark: bool = False) -> str:
    told = set(_load(_told_path(character_id, base), []))
    new = [n for n in _notices(base) if n.get("from") == character_id and n.get("mita_at") and n["id"] not in told]
    if not new:
        return ""
    if mark:
        _save(_told_path(character_id, base), sorted(told | {n["id"] for n in new})[-KEEP:])
    who = config(base)["owner_name"]
    return "\n".join(f"⌚ 時計に送った「{n['text'].replace(chr(10), ' ')}」に、{who}が「見たよ」を返した。" for n in new)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("line", "send", "notice"):
        p = sub.add_parser(name)
        p.add_argument("--character", required=True)
        if name == "send":
            p.add_argument("text")
        if name == "notice":
            p.add_argument("--mark", action="store_true")
    sub.add_parser("status")
    mk = sub.add_parser("make-key")
    mk.add_argument("--owner")
    mk.add_argument("--owner-name")
    a = ap.parse_args(argv)
    if a.cmd == "line":
        s = line(a.character)
        if s:
            print(s)
    elif a.cmd == "send":
        ok, msg = send(a.character, a.text)
        print(msg)
        return 0 if ok else 1
    elif a.cmd == "notice":
        s = notice(a.character, mark=a.mark)
        if s:
            print(s)
    elif a.cmd == "status":
        cfg = config()
        print(json.dumps({"connected": bool(cfg.get("key")), "notify": cfg["notify"], "held": held(),
                          "status": status()}, ensure_ascii=False, indent=2))
    elif a.cmd == "make-key":
        make_key(owner=a.owner, owner_name=a.owner_name)
        print("鍵を作り直した(ダッシュボードの 設定 → 家 → ⌚ ぷち時計 で見られる)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
