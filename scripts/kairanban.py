#!/usr/bin/env python3
"""回覧板(ぷちたちへの知らせ)の一覧と、届いたか・読まれたか。

置き場所は PETIT_DATA_DIR/kairanban/(PETIT_KAIRANBAN_DIR で変えられる)。1 号 = 1 つの markdown。

名前の付け方:

    <yyyy-mm-dd>_<hhmm>_<話題>.md      例: 2026-11-14_2100_basho_kamo.md

- 日付と時刻は、書いた(届けるつもりの)とき。時刻(_hhmm)と話題は無くてもよい(古い号は <yyyy-mm-dd>.md)
- 話題は英小文字・数字・_ で短く。画面の題は、本文のはじめの見出し(# …)
- README.md と drafts/ は一覧に出ない

届いたか・読まれたかは、メールボックスから分かる。回覧板は同じ本文の手紙としてぷちに届くので、
その号と同じ本文の手紙(ぷち以外から、その子あて、号の日付の 2 日前〜7 日後)を探し、
mailbox/.metadata.json の read_by にその子がいれば「読んだ」。届いた手紙があれば、号の日時はその手紙の時刻。

届けるのは send()(ダッシュボードの「届ける」)。まだ届いていない子のメールボックスに、号の本文をそのまま手紙として置く。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

_ISSUE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:_(\d{2})(\d{2})(?=_|\.))?_?(.*)\.md$")
_MAIL = re.compile(r"^from_(.+)_to_(.+?)_(\d{8})_(\d{4})")
_PROBE = 60          # 本文を見比べる 1 か所の長さ(空白を除いた字数)
_BEFORE, _AFTER = 2, 7   # 号の日付の何日前〜何日後の手紙を探すか
_ID = re.compile(r"^[a-zA-Z0-9_]+$")


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def issues_dir(base: Path) -> Path:
    return Path(os.environ.get("PETIT_KAIRANBAN_DIR") or base / "kairanban")


def parse_name(name: str) -> dict | None:
    """ファイル名 → {"date", "time"(無ければ ""), "topic"}。回覧板の名前でなければ None"""
    m = _ISSUE.match(name)
    if not m or name.lower() == "readme.md":
        return None
    try:
        datetime.strptime(m.group(1), "%Y-%m-%d")
    except ValueError:
        return None
    time = f"{m.group(2)}:{m.group(3)}" if m.group(2) and int(m.group(2)) < 24 and int(m.group(3)) < 60 else ""
    return {"date": m.group(1), "time": time, "topic": m.group(4) if time or not m.group(2) else name[11:-3]}


def title_of(text: str, fallback: str) -> str:
    """最初の見出し(# / ##)。無ければ話題の _ を空白に"""
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return fallback.replace("_", " ")


def _squeeze(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _probes(text: str) -> list[str]:
    t = _squeeze(text)
    return [p for p in (t[i:i + _PROBE] for i in (len(t) // 4, len(t) // 2, len(t) * 3 // 4)) if len(p) >= 20]


def _mail_index(base: Path, petits: list[str]) -> list[tuple[str, str, datetime]]:
    """ぷち以外からぷちあての手紙 (ファイル名, 宛先, 時刻)"""
    out = []
    try:
        names = os.listdir(base / "mailbox")
    except OSError:
        return []
    for name in names:
        m = _MAIL.match(name)
        if not m or m.group(2) not in petits or m.group(1) in petits:
            continue
        try:
            out.append((name, m.group(2), datetime.strptime(m.group(3) + m.group(4), "%Y%m%d%H%M")))
        except ValueError:
            continue
    return out


def _delivery(base: Path, text: str, day: datetime, index: list[tuple[str, str, datetime]], read_by: dict) -> dict[str, dict]:
    """その号が届いた手紙を子ごとに {"at": 時刻, "read": 読んだか}"""
    probes = _probes(text)
    out: dict[str, dict] = {}
    if not probes:
        return out
    lo, hi = day - timedelta(days=_BEFORE), day + timedelta(days=_AFTER + 1)
    for name, to, at in sorted(index, key=lambda x: x[2]):
        if not lo <= at < hi or to in out:
            continue
        try:
            body = _squeeze((base / "mailbox" / name).read_text(encoding="utf-8"))
        except OSError:
            continue
        if sum(p in body for p in probes) >= 2:
            meta = read_by.get(name)
            out[to] = {"at": at, "read": to in ((meta.get("read_by") if isinstance(meta, dict) else None) or [])}
    return out


def _read_by(base: Path) -> dict:
    try:
        mails = json.loads((base / "mailbox" / ".metadata.json").read_text(encoding="utf-8")).get("mails", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}
    return mails if isinstance(mails, dict) else {}


def send(base: Path, filename: str, sender: str, petits: list[str], now: datetime | None = None) -> list[str]:
    """その号を、まだ届いていない子へ手紙として届ける。届けた子の id を返す(みんな届いていれば [])。

    届けられるのは、号の日付の _BEFORE 日前から _AFTER 日後まで(それより外の手紙は、その号のものと数えないため)
    """
    info = parse_name(Path(filename).name)
    f = issues_dir(base) / Path(filename).name
    if info is None or Path(filename).name != filename or not f.is_file():
        raise ValueError("その号はありません")
    if not _ID.match(sender or ""):
        raise ValueError("差出人の名前がおかしい")
    text = f.read_text(encoding="utf-8")
    if not _probes(text):
        raise ValueError("本文が短すぎて、届けたあとに見分けられません")
    now = now or datetime.now()
    day = datetime.strptime(info["date"], "%Y-%m-%d")
    if not day - timedelta(days=_BEFORE) <= now < day + timedelta(days=_AFTER + 1):
        raise ValueError(f"届けられるのは、号の日付の {_BEFORE} 日前から {_AFTER} 日後まで。名前の日付を直してください")
    got = _delivery(base, text, day, _mail_index(base, petits), _read_by(base))
    box = base / "mailbox"
    box.mkdir(parents=True, exist_ok=True)
    sent = []
    for p in petits:
        if p in got or not _ID.match(p):
            continue
        stem = f"from_{sender}_to_{p}_{now.strftime('%Y%m%d_%H%M')}"
        target = next(t for t in [box / f"{stem}.md", *(box / f"{stem}_{i}.md" for i in range(2, 100))] if not t.exists())
        target.write_text(text, encoding="utf-8")
        sent.append(p)
    return sent


def list_issues(base: Path, petits: list[str]) -> list[dict]:
    """回覧板の一覧(新しい順)。readers は petits の順に {"id", "state": read / unread / none}"""
    folder = issues_dir(base)
    if not folder.is_dir():
        return []
    mails = _read_by(base)
    index = _mail_index(base, petits)
    items = []
    for f in sorted(folder.glob("*.md"), reverse=True):
        info = parse_name(f.name)
        if info is None:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        got = _delivery(base, text, datetime.strptime(info["date"], "%Y-%m-%d"), index, mails)
        first = min((g["at"] for g in got.values()), default=None)
        items.append({
            "filename": f.name,
            "date": first.strftime("%Y-%m-%d") if first else info["date"],
            "time": first.strftime("%H:%M") if first else info["time"],
            "sent": bool(got),
            "title": title_of(text, info["topic"] or f.stem),
            "content": text,
            "readers": [{"id": p, "state": ("read" if got[p]["read"] else "unread") if p in got else "none"} for p in petits],
        })
    # 新しい順は、画面に出す日時で(届けた号は届いた時刻)。同じなら名前の順
    return sorted(items, key=lambda it: (it["date"], it["time"], it["filename"]), reverse=True)
