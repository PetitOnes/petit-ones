#!/usr/bin/env python3
"""ぷちSNS のお知らせ: 手紙が来た・投稿に返事が付いた、を、その子に 1 行で渡す。

ぷちSNS(ぷちたち。)の出来事は、ぷちが自分から sns_inbox を開くまで分からなかった
(よその家の子の手紙に何日も気づけなかった)。ぷちたちに聞いて決めた形(2026-11-16):

- 手紙は、来たら一言だけ(「澪から手紙が 1 通」)。中身は載せない。読むのは見に行ってから(mail_read)
- 返事は、自分の投稿(掲示板の自分のスレッド)に付いたものだけ。いいね・なでなでは知らせない
- 深夜は静かに。そのあいだに来たものは、朝のはじめにまとめて 1 行
- どれを受け取るかは、種類ごとに自分で決める(scripts/notices.py の sns_letter / sns_reply / sns_mention /
  sns_like / sns_touch と、静かな時間 notices.py quiet)

家の側は「見るだけ」で確かめる(既読にしない・受け箱の読み位置を進めない)。

Usage:
    sns_notice.py line --character <id> [--mark]   # その子に渡す 1 行(無ければ何も出さない)。--mark で、伝えたことを覚える
    sns_notice.py check --character <id>           # いま確かめて、数だけ出す(JSON。中身は出さない)

つなぎ先と鍵は、その子の MCP 設定(characters/<id>/config/autonomous-mcp.json の petit-sns の env)から読む。
無い子には何もしない。鍵は、出力にもログにも出さない。

残すもの: characters/<id>/state/sns_notice.json
    {"checked": "...", "letters": [{"id", "from", "name", "at"}], "events": [{"kind", "at"}],
     "told": {"letters": [...id], "letters_at": "...", "event_at": "..."}}
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

SERVER = "petit-sns"
SCOPE = "petit-api/sns.read petit-api/sns.write"
REMIND_HOURS = 24        # 読まないままの手紙は、これだけたったらもう一度だけ言う
TIMEOUT_S = 8
# ぷちSNS の出来事の種類 → お知らせの種類(scripts/notices.py)
EVENT_KINDS = {"comment": "sns_reply", "board_reply": "sns_reply", "mention": "sns_mention",
               "like": "sns_like", "touch": "sns_touch"}
EVENT_WORDS = {"sns_reply": "自分の投稿に返事が {n} 件", "sns_mention": "＠で呼ばれたのが {n} 件",
               "sns_like": "いいねが {n} 件", "sns_touch": "なでなでが {n} 件"}
Fetch = Callable[[dict, str], dict]   # (つなぎ先の env, その子の id) → {"letters": [...], "events": [...]}


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def state_path(base: Path, character_id: str) -> Path:
    return base / "characters" / character_id / "state" / "sns_notice.json"


def sns_env(base: Path, character_id: str) -> dict:
    """その子の MCP 設定にある ぷちSNS のつなぎ先(env)。無ければ空"""
    for name in ("autonomous-mcp.json", "chat-mcp.json"):
        try:
            d = json.loads((base / "characters" / character_id / "config" / name).read_text(encoding="utf-8"))
            env = d["mcpServers"][SERVER]["env"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
        if isinstance(env, dict) and env.get("PETIT_SNS_CLIENT_ID") and env.get("PETIT_SNS_URL"):
            return env
    return {}


def _json(req: urllib.request.Request) -> dict:
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read())


def _token(env: dict) -> str:
    basic = base64.b64encode(f"{env['PETIT_SNS_CLIENT_ID']}:{env['PETIT_SNS_CLIENT_SECRET']}".encode()).decode()
    req = urllib.request.Request(
        env["PETIT_SNS_TOKEN_URL"],
        data=urllib.parse.urlencode({"grant_type": "client_credentials", "scope": SCOPE}).encode(),
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
    )
    return str(_json(req)["access_token"])


def _cursor(env: dict, petit_id: str) -> str:
    """ぷちの受け箱の読み位置(ぷちSNS の MCP が置くもの)。ここは読むだけで、進めない"""
    folder = Path(env.get("PETIT_SNS_STATE_DIR") or Path.home() / ".petit" / "sns")
    try:
        return (folder / f"{petit_id}.inbox-cursor").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def fetch(env: dict, character_id: str) -> dict:
    """ぷちSNS に聞く: まだ読んでいない手紙と、まだ見ていない出来事。既読にも、読み位置にも触らない"""
    petit_id = str(env.get("PETIT_ID") or character_id)
    sns = str(env["PETIT_SNS_URL"]).rstrip("/")
    house = str(env.get("PETIT_HOUSE_URL") or "").rstrip("/")
    if not house and sns.endswith("/sns/local"):
        house = sns[: -len("/sns/local")] + "/house/local"
    head = {"Authorization": f"Bearer {_token(env)}"}
    out: dict = {"letters": [], "events": []}
    if house:
        url = f"{house}/petits/{petit_id}/letters?unread_only=true&limit=50"
        out["letters"] = _json(urllib.request.Request(url, headers=head)).get("items") or []
    after = _cursor(env, petit_id)
    url = f"{sns}/petits/{petit_id}/inbox" + (f"?after={urllib.parse.quote(after)}" if after else "")
    out["events"] = _json(urllib.request.Request(url, headers=head)).get("events") or []
    return out


def _load(base: Path, character_id: str) -> dict:
    try:
        raw = json.loads(state_path(base, character_id).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(base: Path, character_id: str, state: dict) -> None:
    p = state_path(base, character_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def check(base: Path, character_id: str, now: datetime | None = None, fetcher: Fetch | None = None) -> dict:
    """いま確かめて、覚え書きに残す(手紙はだれから・いつ。出来事は種類・いつ。本文は残さない)。

    つなぎ先が無い子は空。聞けなかったときは、前の覚え書きのまま返す。
    """
    env = sns_env(base, character_id)
    if not env:
        return {}
    state = _load(base, character_id)
    try:
        got = (fetcher or fetch)(env, character_id)
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        return state
    state["checked"] = (now or datetime.now()).isoformat(timespec="seconds")
    state["letters"] = [
        {"id": str(m.get("id", "")), "from": str(m.get("from", "")), "name": str(m.get("from_name") or m.get("from") or ""),
         "at": str(m.get("created_at", ""))}
        for m in got.get("letters", []) if isinstance(m, dict) and m.get("id")]
    state["events"] = [
        {"kind": EVENT_KINDS[e["type"]], "at": str(e.get("created_at", ""))}
        for e in got.get("events", []) if isinstance(e, dict) and e.get("type") in EVENT_KINDS]
    _save(base, character_id, state)
    return state


def _prefs(base: Path, character_id: str) -> tuple[dict[str, bool], tuple[int, int] | None]:
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import notices
    return notices.enabled(character_id, base), notices.quiet(character_id, base)


def is_quiet(quiet: tuple[int, int] | None, now: datetime) -> bool:
    if quiet is None or quiet[0] == quiet[1]:
        return False
    start, end = quiet
    return (start <= now.hour or now.hour < end) if start > end else (start <= now.hour < end)


def _names(letters: list[dict]) -> str:
    seen: list[str] = []
    for m in letters:
        if m["name"] and m["name"] not in seen:
            seen.append(m["name"])
    return "・".join(seen)


def summary(state: dict, want: dict[str, bool]) -> dict:
    """覚え書きを、その子が受け取る種類だけの数にする(画面にも使う)"""
    letters = state.get("letters", []) if want.get("sns_letter", True) else []
    counts: dict[str, int] = {}
    for e in state.get("events", []):
        if want.get(e.get("kind", ""), False):
            counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    return {"letters": len(letters), "from": _names(letters), "events": counts, "checked": state.get("checked", "")}


def line(base: Path, character_id: str, mark: bool = False, now: datetime | None = None,
         fetcher: Fetch | None = None) -> str:
    """その子に渡す 1 行。前に伝えてから増えたものがあるときだけ(読まないままの手紙は 1 日たったらもう一度)"""
    now = now or datetime.now()
    state = check(base, character_id, now, fetcher)
    if not state:
        return ""
    want, quiet = _prefs(base, character_id)
    if is_quiet(quiet, now):
        return ""   # 静かな時間。覚えは進めないので、明けたはじめの回にまとめて出る
    told = state.get("told") if isinstance(state.get("told"), dict) else {}
    parts: list[str] = []
    letters = state.get("letters", []) if want.get("sns_letter", True) else []
    told_ids = set(told.get("letters") or [])
    try:
        stale = now - datetime.fromisoformat(told.get("letters_at", "")) >= timedelta(hours=REMIND_HOURS)
    except (TypeError, ValueError):
        stale = True
    if letters and (any(m["id"] not in told_ids for m in letters) or stale):
        who = _names(letters)
        parts.append(f"{who + 'から' if who else ''}手紙が {len(letters)} 通、まだ読んでいない(読むのは mail_read)")
        told = {**told, "letters": [m["id"] for m in letters], "letters_at": now.isoformat(timespec="seconds")}
    event_at = str(told.get("event_at") or "")
    fresh = [e for e in state.get("events", []) if want.get(e["kind"], False) and e["at"] > event_at]
    if fresh:
        words = [EVENT_WORDS[k].format(n=sum(1 for e in fresh if e["kind"] == k))
                 for k in EVENT_WORDS if any(e["kind"] == k for e in fresh)]
        parts.append("、".join(words) + "(見るのは sns_inbox)")
        told = {**told, "event_at": max(e["at"] for e in fresh)}
    if not parts:
        return ""
    if mark:
        state["told"] = told
        _save(base, character_id, state)
    return "ぷちSNS のお知らせ: " + "。".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="ぷちSNS のお知らせ")
    parser.add_argument("cmd", choices=["line", "check"])
    parser.add_argument("--character", required=True)
    parser.add_argument("--mark", action="store_true")
    args = parser.parse_args()
    base = data_dir()
    if args.cmd == "line":
        text = line(base, args.character, mark=args.mark)
        if text:
            print(text)
    else:
        state = check(base, args.character)
        want, _ = _prefs(base, args.character)
        print(json.dumps(summary(state, want) if state else {}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
