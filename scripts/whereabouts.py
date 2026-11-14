#!/usr/bin/env python3
"""いま どこ: 家の人の「いま」(自室・お外・会社 など)と、ぷちの体がどこにいるか(家 / お外)。

人の「いま」は、ダッシュボードの右上(📍)で人が決める。置き場所は PETIT_DATA_DIR/state/whereabouts.json:

    {"users": {"arisan": {"text": "会社", "since": "2026-11-14T09:02:11"}},
     "recent": ["会社", "自室", "お外"]}

- users: ログインのユーザー名ごとに、いまの一言と、そうなった時刻。空にすると消える
- recent: 使った言葉(新しい順、RECENT_MAX 件)。ボタンの候補にする。はじめの候補は PRESETS

ぷちの体の居場所は、体がどの Wi-Fi につながっているかから決める(人は何もしない)。
体験デーモン(experience-daemon)が characters/<id>/state/experience_state.json に、体の /status の wifi(何番目の Wi-Fi か)と
ip、つないだ先(host)、最後に見えた時刻(seen)を書く。どの番号がどこかは PETIT_DATA_DIR/config/places.json(無ければ DEFAULT_PLACES):

    {"wifi": {"1": "家", "2": "家", "3": "お外"},
     "how":  {"1": "家の Wi-Fi", "2": "家の Wi-Fi", "3": "テザリング"},
     "hosts": {"192.168.": "家", "100.": "お外"}}

- wifi: 体の Wi-Fi の何番目(firmware の config.h の WIFI1/2/3)がどこか。how はその言い方
- hosts: wifi の番号が無い(古いファーム)とき、つないだ先のアドレスの頭で決める
- デーモンが BODY_STALE_S より長く何も書いていなければ、体のことは分からない(何も出さない)

ぷちに渡す行(会話の system prompt と自律行動の冒頭):

    ありさんのいま: 会社(9:02 から)
    あなたの体のいま: 家(家の Wi-Fi)
    ぷちこの体のいま: お外(テザリング)
    ぷちるの体: いまは見えない(12:50 から)

Usage:
    python3 whereabouts.py line [--character <id>]   # ぷちに渡す行(--character でその子を「あなた」に)。無ければ何も出さない
    python3 whereabouts.py set <ユーザー名> "<一言>"   # 人のいまを決める。一言が空なら消す
    python3 whereabouts.py show                       # いまの中身(JSON)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PRESETS = ["自室", "お外", "会社"]
RECENT_MAX = 8
TEXT_MAX = 30
BODY_STALE_S = 300   # デーモンがこれより長く書いていなければ、体のことは分からない
DEFAULT_PLACES = {
    "wifi": {"1": "家", "2": "家", "3": "お外"},
    "how": {"1": "家の Wi-Fi", "2": "家の Wi-Fi", "3": "テザリング"},
    "hosts": {"192.168.": "家", "100.": "お外"},
}
UNSEEN = "いまは見えない"


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def path(base: Path | None = None) -> Path:
    return (base or data_dir()) / "state" / "whereabouts.json"


# ---- 人の「いま」 ----

def load(base: Path | None = None) -> dict:
    try:
        d = json.loads(path(base).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    users = d.get("users") if isinstance(d.get("users"), dict) else {}
    recent = [r for r in d.get("recent", []) if isinstance(r, str)] if isinstance(d.get("recent"), list) else []
    return {"users": {k: v for k, v in users.items() if isinstance(v, dict) and v.get("text")}, "recent": recent}


def save(d: dict, base: Path | None = None) -> None:
    p = path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def clean_text(text: str) -> str:
    text = " ".join((text or "").split())
    if len(text) > TEXT_MAX:
        raise ValueError(f"一言は {TEXT_MAX} 文字まで")
    return text


def set_status(user: str, text: str, base: Path | None = None, now: datetime | None = None) -> dict:
    """その人のいまを決める(text が空なら消す)。使った言葉は recent の先頭に"""
    text = clean_text(text)
    d = load(base)
    if text:
        d["users"][user] = {"text": text, "since": (now or datetime.now()).replace(microsecond=0).isoformat()}
        d["recent"] = ([text] + [r for r in d["recent"] if r != text])[:RECENT_MAX]
    else:
        d["users"].pop(user, None)
    save(d, base)
    return d


def choices(d: dict) -> list[str]:
    """ボタンに並べる候補: はじめの候補 + 使った言葉(重複なし)"""
    out = list(PRESETS)
    out += [r for r in d.get("recent", []) if r not in out]
    return out


def _since_words(since: str, now: datetime) -> str:
    try:
        t = datetime.fromisoformat(since)
    except (TypeError, ValueError):
        return ""
    if t.date() == now.date():
        return f"{t.hour}:{t.minute:02d} から"
    if (now.date() - t.date()).days == 1:
        return f"きのう {t.hour}:{t.minute:02d} から"
    return f"{t.month}/{t.day} から"


def people_lines(d: dict, label=lambda u: u, now: datetime | None = None) -> list[str]:
    """「ありさんのいま: 会社(9:02 から)」"""
    now = now or datetime.now()
    out = []
    for user, cur in d.get("users", {}).items():
        since = _since_words(cur.get("since", ""), now)
        out.append(f"{label(user)}のいま: {cur['text']}" + (f"({since})" if since else ""))
    return out


# ---- ぷちの体 ----

def load_places(base: Path | None = None) -> dict:
    places = {k: dict(v) for k, v in DEFAULT_PLACES.items()}
    try:
        raw = json.loads(((base or data_dir()) / "config" / "places.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return places
    for k in places:
        if isinstance(raw.get(k), dict):
            places[k].update({str(a): str(b) for a, b in raw[k].items()})
    return places


def place_of(net: dict, places: dict) -> tuple[str, str]:
    """体の net(wifi・host)→(場所, どうして)。分からなければ ("", "")"""
    wifi = net.get("wifi")
    if wifi is not None and str(wifi) in places["wifi"]:
        return places["wifi"][str(wifi)], places["how"].get(str(wifi), "")
    host = str(net.get("host") or "")
    for prefix, place in places["hosts"].items():
        if host.startswith(prefix):
            return place, ""
    return "", ""


def body(character_id: str, base: Path | None = None, now: datetime | None = None) -> dict | None:
    """その子の体のいま。デーモンの記録が無い・古いなら None"""
    now = now or datetime.now()
    f = (base or data_dir()) / "characters" / character_id / "state" / "experience_state.json"
    try:
        st = json.loads(f.read_text(encoding="utf-8"))
        seen = datetime.fromisoformat(st.get("seen") or "")
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if (now - seen).total_seconds() > BODY_STALE_S:
        return None
    net = st.get("net") if isinstance(st.get("net"), dict) else {}
    if st.get("state") == "offline" or not net:
        return {"place": "", "how": "", "since": st.get("since", ""), "offline": True}
    place, how = place_of(net, load_places(base))
    return {"place": place, "how": how, "since": net.get("since", ""), "offline": False}


def body_line(name: str, b: dict, now: datetime, me: bool = False) -> str:
    """「ぷちてゃの体のいま: 家(家の Wi-Fi、12:30 から)」。自分なら「あなたの体のいま: …」"""
    who = "あなたの体" if me else f"{name}の体"
    since = _since_words(b.get("since", ""), now)
    if b.get("offline"):
        return f"{who}: {UNSEEN}" + (f"({since})" if since else "")
    if not b.get("place"):
        return ""
    detail = "、".join(x for x in (b.get("how", ""), since) if x)
    return f"{who}のいま: {b['place']}" + (f"({detail})" if detail else "")


def characters(base: Path | None = None) -> list[tuple[str, str]]:
    """家の子 [(id, 名前)](characters/*/config/config.json)"""
    out = []
    root = (base or data_dir()) / "characters"
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        try:
            cfg = json.loads((d / "config" / "config.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append((d.name, cfg.get("name") or d.name))
    return out


def lines(base: Path | None = None, me: str | None = None, label=None, now: datetime | None = None) -> list[str]:
    """ぷちに渡す行ぜんぶ: 人のいま + 体のいま(me の子を先に「あなたの体」として)"""
    now = now or datetime.now()
    out = people_lines(load(base), label or _people_label(base), now)
    chars = characters(base)
    chars.sort(key=lambda c: c[0] != me)
    for cid, name in chars:
        b = body(cid, base, now)
        if b:
            line = body_line(name, b, now, me=(cid == me))
            if line:
                out.append(line)
    return out


def _people_label(base: Path | None):
    try:
        people = json.loads(((base or data_dir()) / "config" / "people.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        people = {}
    return lambda u: (people.get(u) or {}).get("name") or u


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_line = sub.add_parser("line")
    p_line.add_argument("--character", default=None)
    sub.add_parser("show")
    p_set = sub.add_parser("set")
    p_set.add_argument("user")
    p_set.add_argument("text")
    a = ap.parse_args()
    base = data_dir()
    if a.cmd == "line":
        for line in lines(base, me=a.character):
            print(line)
    elif a.cmd == "show":
        print(json.dumps({"people": load(base), "bodies": {cid: body(cid, base) for cid, _ in characters(base)}}, ensure_ascii=False, indent=2))
    elif a.cmd == "set":
        try:
            set_status(a.user, a.text, base)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
