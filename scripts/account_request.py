#!/usr/bin/env python3
"""ログイン画面からのお願い: 新規登録と、パスワードの出し直し。

ログインの前の人が送れるのは「お願い」だけ。アカウントを作る・パスワードを決めるのは、家の持ち主が手でやる。
お願いは、家の手紙箱に、家の持ち主への手紙として入る(持ち主の「メール」に未読で出る)。

決まり:
- パスワードは受け取らない(手紙箱に、パスワードを書いた手紙を残さない)
- パスワードの出し直しでは、そのユーザー名がいるかどうかを、送った人に教えない(いつも同じ返事)
- 送りすぎを止める: 同じ場所(IP)から 1 時間に PER_IP 通まで、家ぜんたいで 1 日に PER_DAY 通まで
- 長さを切る。ユーザー名は英数字と _ だけ
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

SENDER = "login"   # 手紙箱での差出人の ID(ぷち・人の ID と重ならない名前)
PER_IP = 3
PER_DAY = 12
KINDS = {"signup": "新規登録のお願い", "reset": "パスワードの出し直しのお願い"}
_USERNAME = re.compile(r"^[a-zA-Z0-9_]{1,30}$")


class RequestError(ValueError):
    """受け取れないお願い。メッセージは人に見せてよい文"""


def clean(kind: str, username: str, name: str = "", note: str = "") -> dict:
    """中身を確かめて、手紙に書ける形にする。だめなら RequestError"""
    if kind not in KINDS:
        raise RequestError("お願いの種類が分かりません")
    username = (username or "").strip()
    if not _USERNAME.match(username):
        raise RequestError("ユーザー名は、英数字と _ で 30 字までにしてください")
    one_line = lambda t, n: " ".join(str(t or "").split())[:n]   # noqa: E731
    name, note = one_line(name, 30) if kind == "signup" else "", one_line(note, 300)   # 呼び名は、新規登録だけ
    if kind == "signup" and not name:
        raise RequestError("呼び名を書いてください")
    if not note:
        raise RequestError("ひとこと(だれか分かるように)を書いてください")
    return {"kind": kind, "username": username, "name": name, "note": note}


class Limiter:
    """送りすぎを止める(覚えるのは、この プロセスが動いているあいだだけ)"""

    def __init__(self, per_ip: int = PER_IP, per_day: int = PER_DAY):
        self.per_ip, self.per_day = per_ip, per_day
        self.sent: list[tuple[datetime, str]] = []

    def allow(self, ip: str, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        self.sent = [(t, i) for t, i in self.sent if now - t < timedelta(days=1)]
        if len(self.sent) >= self.per_day:
            return False
        if sum(1 for t, i in self.sent if i == ip and now - t < timedelta(hours=1)) >= self.per_ip:
            return False
        self.sent.append((now, ip))
        return True


def letter(req: dict, ip: str, exists: bool) -> str:
    """家の持ち主に届く手紙の文。exists: そのユーザー名が、もう家にいるか"""
    lines = [f"【ログイン画面から: {KINDS[req['kind']]}】", "", f"ユーザー名: {req['username']}"]
    if req["name"]:
        lines.append(f"呼び名: {req['name']}")
    lines += [f"ひとこと: {req['note']}", f"送ってきた場所: {ip or '分からない'}", ""]
    if req["kind"] == "signup":
        lines.append("※ このユーザー名は、もう使われています。別の名前にしてもらってください。" if exists else
                     "受けるなら: auth.json の users に足して、決めたパスワードを本人に伝えてください。")
    else:
        lines.append("出し直すなら: auth.json のその人の password を変えて、本人に伝えてください。" if exists else
                     "※ このユーザー名の人は、家にいません。")
    lines += ["", "ログイン画面"]
    return "\n".join(lines) + "\n"


def write(mailbox: Path, owner: str, text: str, now: datetime | None = None) -> Path:
    """手紙箱に 1 通書く。同じ分にもう 1 通あっても上書きしない"""
    now = now or datetime.now()
    mailbox.mkdir(parents=True, exist_ok=True)
    stem = f"from_{SENDER}_to_{owner}_{now.strftime('%Y%m%d_%H%M')}"
    path, n = mailbox / f"{stem}.md", 2
    while path.exists():
        path, n = mailbox / f"{stem}_{n}.md", n + 1
    path.write_text(text, encoding="utf-8")
    return path
