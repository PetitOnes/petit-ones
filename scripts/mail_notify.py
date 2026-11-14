#!/usr/bin/env python3
"""手紙が届いたことを、Slack で人に知らせる(スマホの通知用)。

家の手紙箱(mailbox/)に、その人あての新しい手紙があれば、Slack に 1 行だけ送る。
本文は送らない(家の中の言葉を、外のサービスに写さない)。送るのは「だれから、何通」だけ。

Usage:
    mail_notify.py run       # 新しく届いた分を知らせる(cron で 5 分ごと)
    mail_notify.py status    # 設定と、まだ知らせていない数

設定は PETIT_DATA_DIR/config/mail_notify.json(ダッシュボードの ⚙️ 設定 → Slack 通知 で、人ごとに決める):

    {"users": {"<ユーザー名>": {"on": true, "to": "<Slack のチャンネル ID かメンバー ID>", "house": false, "quiet": [0, 7]}}}

- on: 知らせるか
- to: 送り先。空で house が true なら、家の知らせと同じチャンネル(.env の HOUSE_ALERT_SLACK_CHANNEL、無ければ SLACK_APPROVE_CHANNEL)。
  house は、家の世話人が送り先を空のまま決めたときにダッシュボードが付ける
- quiet: [はじまり, おわり] の時(0〜23)。このあいだは送らず、明けてからまとめて 1 回。null なら、いつでも送る

決まり:
- 知らせるのは、まだ読んでいない手紙だけ(ダッシュボードで読んだものは、数えない)
- 家の知らせ(from_house_…)は数えない(それ自体が Slack にも出ている)
- はじめての回は、いまある手紙を「知らせた」ことにして、何も送らない(昔の手紙をまとめて数えないため)
- 覚え書きは PETIT_DATA_DIR/state/mail_notify.json。ボットの鍵は .env の SLACK_APPROVE_BOT_TOKEN
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_NAME = re.compile(r"^from_(.+)_to_(.+?)_(\d{8})_(\d{4})")
_SLACK_ID = re.compile(r"^[A-Z0-9]{6,20}$")
TOLD_MAX = 400          # 覚えておく「知らせた手紙」の数
SKIP_FROM = {"house"}   # 数えない差出人
NAMES_SHOWN = 4         # 1 行に名前を書く差出人の数


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def config_path(base: Path) -> Path:
    return base / "config" / "mail_notify.json"


def clean(raw: object) -> dict:
    """1 人分の設定を、決まった形に。おかしい値は ValueError(メッセージは人に見せてよい文)"""
    raw = raw if isinstance(raw, dict) else {}
    to = str(raw.get("to") or "").strip()
    if to and not _SLACK_ID.match(to):
        raise ValueError("送り先は、Slack のチャンネル ID(C…)かメンバー ID(U…)を入れてください")
    quiet = raw.get("quiet")
    if quiet is not None:
        try:
            quiet = [int(quiet[0]), int(quiet[1])]
        except (TypeError, ValueError, IndexError) as e:
            raise ValueError("出さない時間は、0〜23 の時で入れてください") from e
        if not all(0 <= h <= 23 for h in quiet):
            raise ValueError("出さない時間は、0〜23 の時で入れてください")
        if quiet[0] == quiet[1]:
            quiet = None
    return {"on": raw.get("on") is True, "to": to, "house": raw.get("house") is True, "quiet": quiet}


def load_user(base: Path, user: str) -> dict:
    users = _json(config_path(base), {}).get("users", {})
    try:
        return clean(users.get(user) if isinstance(users, dict) else None)
    except ValueError:
        return clean(None)


def save_user(base: Path, user: str, raw: object) -> dict:
    cur = clean(raw)
    d = _json(config_path(base), {})
    d = d if isinstance(d, dict) else {}
    users = d.get("users") if isinstance(d.get("users"), dict) else {}
    users[user] = cur
    d["users"] = users
    p = config_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return cur


def is_quiet(quiet: list[int] | None, now: datetime) -> bool:
    if not quiet:
        return False
    start, end = quiet
    return (start <= now.hour < end) if start < end else (now.hour >= start or now.hour < end)


def unread_for(base: Path, user: str) -> list[tuple[str, str]]:
    """その人あての、まだ読んでいない手紙 [(ファイル名, 差出人)](古い順)"""
    mails = _json(base / "mailbox" / ".metadata.json", {}).get("mails", {})
    mails = mails if isinstance(mails, dict) else {}
    out = []
    try:
        names = sorted(os.listdir(base / "mailbox"))
    except OSError:
        return []
    for name in names:
        m = _NAME.match(name)
        if not m or m.group(2) != user or m.group(1) in SKIP_FROM or not name.endswith(".md"):
            continue
        meta = mails.get(name)
        if isinstance(meta, dict) and (user in (meta.get("read_by") or []) or meta.get("archived")):
            continue
        out.append((name, m.group(1)))
    return sorted(out, key=lambda x: _NAME.match(x[0]).group(3, 4))


def _names(base: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        import whereabouts
        out.update(dict(whereabouts.characters(base)))
    except Exception:
        pass
    people = _json(base / "config" / "people.json", {})
    for k, v in people.items() if isinstance(people, dict) else []:
        if isinstance(v, dict) and v.get("name"):
            out[k] = str(v["name"])
    return out


def message(senders: list[str], names: dict[str, str]) -> str:
    """Slack に送る 1 行。本文は入れない"""
    counts: dict[str, int] = {}
    for s in senders:
        counts[s] = counts.get(s, 0) + 1
    order = sorted(counts, key=lambda s: -counts[s])
    parts = [f"{names.get(s, s)} {counts[s]}" for s in order[:NAMES_SHOWN]]
    if len(order) > NAMES_SHOWN:
        parts.append(f"ほか {sum(counts[s] for s in order[NAMES_SHOWN:])}")
    return f"📬 手紙が {len(senders)} 通届いています({'、'.join(parts)})"


def _channel(cfg: dict) -> str:
    if cfg["to"]:
        return cfg["to"]
    if not cfg["house"]:
        return ""
    import slack_notify
    return slack_notify.load_env_value("HOUSE_ALERT_SLACK_CHANNEL") or slack_notify.load_env_value("SLACK_APPROVE_CHANNEL") or ""


def _slack(text: str, channel: str) -> bool:
    import slack_notify
    try:
        return slack_notify.send(text, channel)
    except Exception as e:   # 送れなくても、次の回にまた試す
        print(f"[mail-notify] Slack に送れなかった: {type(e).__name__}", file=sys.stderr)
        return False


def run(base: Path, now: datetime | None = None, send: Callable[[str, str], bool] | None = None) -> list[tuple[str, int]]:
    """人ごとに、新しく届いた手紙を知らせる。知らせた (人, 通数) を返す"""
    now = now or datetime.now()
    send = send or _slack
    users = _json(config_path(base), {}).get("users", {})
    state_path = base / "state" / "mail_notify.json"
    state = _json(state_path, {})
    state = state if isinstance(state, dict) else {}
    names = None
    out = []
    for user in users if isinstance(users, dict) else []:
        cfg = load_user(base, user)
        unread = unread_for(base, user)
        if user not in state:   # はじめての回: いまあるものは、知らせたことに
            state[user] = [n for n, _ in unread][-TOLD_MAX:]
            continue
        told = set(state[user])
        fresh = [(n, s) for n, s in unread if n not in told]
        if not cfg["on"]:   # 止めているあいだに届いた分は、あとでまとめて知らせない
            state[user] = (state[user] + [n for n, _ in fresh])[-TOLD_MAX:]
            continue
        channel = _channel(cfg)
        if not fresh or not channel or is_quiet(cfg["quiet"], now):
            continue
        names = names if names is not None else _names(base)
        if send(message([s for _, s in fresh], names), channel):
            state[user] = (state[user] + [n for n, _ in fresh])[-TOLD_MAX:]
            out.append((user, len(fresh)))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp.replace(state_path)
    return out


def try_send(base: Path, user: str, send: Callable[[str, str], bool] | None = None) -> bool:
    """ためしに 1 行送る(設定ページの「ためしに送る」)。送り先が無ければ ValueError"""
    channel = _channel(load_user(base, user))
    if not channel:
        raise ValueError("送り先が決まっていません。Slack のチャンネル ID かメンバー ID を入れてください")
    return (send or _slack)("📬 手紙の通知のためしです。ここに「だれから、何通」が届きます", channel)


def main() -> int:
    ap = argparse.ArgumentParser(description="手紙が届いたことを Slack で知らせる")
    ap.add_argument("cmd", choices=["run", "status"])
    a = ap.parse_args()
    base = data_dir()
    if a.cmd == "run":
        for user, n in run(base):
            print(f"{user}: {n} 通を知らせた")
        return 0
    users = _json(config_path(base), {}).get("users", {})
    state = _json(base / "state" / "mail_notify.json", {})
    for user in users if isinstance(users, dict) else []:
        cfg = load_user(base, user)
        waiting = [n for n, _ in unread_for(base, user) if n not in set(state.get(user, []))] if user in state else []
        print(f"{user}: {'出す' if cfg['on'] else '出さない'} / 送り先 {'あり' if _channel(cfg) else 'なし'} / 出さない時間 {cfg['quiet'] or 'なし'} / まだ知らせていない {len(waiting)} 通")
    return 0


if __name__ == "__main__":
    sys.exit(main())
