#!/usr/bin/env python3
"""家の知らせ: ぷちが Claude を呼べなかったとき・何かが失敗したときに、世話人へ知らせる。

2026-11-14 の朝、ぷち用のログインが切れて 6 時間だれも Claude を呼べていなかったのに、
ログを開くまで気づけなかった。そこで、失敗を見つけたら人に届くところへ出す。

Usage:
    house_alert.py check-stream --source autonomous --character <id> --stream <stream.jsonl>
    house_alert.py report --kind <kind> --source <どこで> [--character <id>] --detail "<理由>"
    house_alert.py ok --kind <kind> [--source <どこで>] [--character <id>]
    house_alert.py status

決まり:
    - ログイン切れは、最初の 1 回をすぐ知らせる。ほかの失敗は、つづけて 2 回(HOUSE_ALERT_MIN_COUNT)起きたら知らせる
      (会話を途中で止めた・ダッシュボードを入れ直した、のような 1 回きりの失敗では鳴らさない)
    - 続いているあいだは HOUSE_ALERT_REPEAT_HOURS(既定 3)時間ごとに 1 回
    - 直ったら(同じ種類が次に成功したら)1 回だけ「直りました」と知らせる
    - 知らせる先は Slack(.env の HOUSE_ALERT_SLACK_CHANNEL、無ければ SLACK_APPROVE_CHANNEL)
    - 覚え書きは PETIT_DATA_DIR/state/house_alerts.json
    - HOUSE_ALERT=0 で止められる。知らせに失敗しても、呼んだ側の仕事は止めない
    - 知らせの文に、鍵・IP・会話の中身を入れない(理由の文は頭 200 字、鍵らしい並びは伏せる)
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

KIND_LABELS = {
    "claude_auth": "ぷちが Claude を呼べていません(ログインが切れています)",
    "claude_network": "ぷちが Claude を呼べていません(ネットワークにつながりません)",
    "claude_limit": "ぷちが Claude を呼べていません(使用量の上限か、混雑です)",
    "claude_error": "ぷちの Claude がエラーで終わりました",
    "claude_no_result": "ぷちの Claude が、結果を返さずに終わりました",
}
KIND_HINTS = {
    "claude_auth": "確かめ方: `CLAUDE_CONFIG_DIR=<家>/.claude claude auth status`。直し方は docs/operations.md の「家の知らせ」",
    "claude_network": "PC のネットワークと DNS を見てください。つながれば次の回から戻ります",
}
CLAUDE_KINDS = tuple(KIND_LABELS)
AT_ONCE_KINDS = ("claude_auth",)   # 1 回目ですぐ知らせる種類(自然には直らない)
DETAIL_MAX = 200

_SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|xox[a-z]-[A-Za-z0-9-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|[A-Za-z0-9+/_=-]{32,})")
_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def data_dir() -> Path:
    return Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))


def state_path(base: Path) -> Path:
    return base / "state" / "house_alerts.json"


def clean_detail(text: str) -> str:
    """理由の文を、人に見せてよい形にする: 1 行・200 字まで・鍵らしい並びと IP は伏せる。"""
    one = " ".join(str(text or "").split())
    one = _SECRET.sub("***", one)
    one = _IP.sub("<ip>", one)
    return one[:DETAIL_MAX]


def classify(result: dict | None) -> tuple[str | None, str]:
    """Claude の最後の結果(stream-json の result 行)から、失敗の種類と理由を返す。失敗でなければ (None, "")。"""
    if not result:
        return "claude_no_result", ""
    if not result.get("is_error"):
        return None, ""
    text = str(result.get("result") or result.get("subtype") or "")
    low = text.lower()
    if "authenticate" in low or "oauth" in low or "401" in low or "invalid api key" in low or "/login" in low:
        return "claude_auth", text
    if "reach the api" in low or "eai_again" in low or "econn" in low or "network" in low or "dns" in low:
        return "claude_network", text
    if "limit" in low or "overloaded" in low or "429" in low or "529" in low:
        return "claude_limit", text
    return "claude_error", text


def read_result(stream: Path) -> dict | None:
    """stream.jsonl の最初の result 行を返す。無ければ None。"""
    try:
        with stream.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"type":"result"' not in line and '"type": "result"' not in line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(ev, dict) and ev.get("type") == "result":
                    return ev
    except OSError:
        return None
    return None


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class _Locked:
    """覚え書きを、ほかの子の回と同時に書かないための鍵。"""

    def __init__(self, base: Path):
        self.path = state_path(base).with_suffix(".lock")

    def __enter__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = self.path.open("w")
        fcntl.flock(self.f, fcntl.LOCK_EX)

    def __exit__(self, *exc: object) -> None:
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def _where(source: str, character: str) -> str:
    return f"{character} の {source}" if character else source


def _send_slack(text: str) -> bool:
    import slack_notify

    channel = slack_notify.load_env_value("HOUSE_ALERT_SLACK_CHANNEL") or None
    return slack_notify.send(text, channel)


def _enabled() -> bool:
    return os.getenv("HOUSE_ALERT", "1") != "0"


def repeat_hours() -> float:
    try:
        return float(os.getenv("HOUSE_ALERT_REPEAT_HOURS", "3"))
    except ValueError:
        return 3.0


def min_count(kind: str) -> int:
    if kind in AT_ONCE_KINDS:
        return 1
    try:
        return max(1, int(os.getenv("HOUSE_ALERT_MIN_COUNT", "2")))
    except ValueError:
        return 2


def report(base: Path, kind: str, source: str, character: str = "", detail: str = "",
           now: datetime | None = None, send: Callable[[str], bool] | None = None) -> str | None:
    """失敗を 1 件覚える。知らせを出したら、その文を返す(出さなければ None)。"""
    now = now or datetime.now()
    send = send or _send_slack
    detail = clean_detail(detail)
    with _Locked(base):
        state = _load(state_path(base))
        item = state.get(kind) or {"first": now.isoformat(timespec="seconds"), "count": 0, "where": []}
        item["count"] = int(item.get("count", 0)) + 1
        item["last"] = now.isoformat(timespec="seconds")
        item["detail"] = detail
        where = _where(source, character)
        if where not in item["where"]:
            item["where"].append(where)

        notified = item.get("notified")
        if notified is None:
            due = item["count"] >= min_count(kind)
        else:
            due = now - datetime.fromisoformat(notified) >= timedelta(hours=repeat_hours())
        text = None
        if due and _enabled():
            label = KIND_LABELS.get(kind, f"家で失敗がありました({kind})")
            first = datetime.fromisoformat(item["first"])
            lines = [f"[house-alert] {label}"]
            if item["count"] == 1:
                lines.append(f"{now.strftime('%m/%d %H:%M')} {where}")
            else:
                lines.append(f"{first.strftime('%m/%d %H:%M')} から {item['count']} 回({'、'.join(item['where'])})")
            if detail:
                lines.append(f"理由: {detail}")
            if kind in KIND_HINTS:
                lines.append(KIND_HINTS[kind])
            text = "\n".join(lines)
            try:
                sent = send(text)
            except Exception as e:  # 知らせに失敗しても、呼んだ側の仕事は止めない
                print(f"[house-alert] 知らせを送れなかった: {type(e).__name__}", file=sys.stderr)
                sent = False
            if sent:
                item["notified"] = now.isoformat(timespec="seconds")
            else:
                text = None
        state[kind] = item
        _save(state_path(base), state)
    return text


def ok(base: Path, kinds: tuple[str, ...] | list[str], source: str = "", character: str = "",
       now: datetime | None = None, send: Callable[[str], bool] | None = None) -> str | None:
    """うまくいった。続いていた失敗があれば消して、知らせ済みのものは「直りました」を 1 回出す。"""
    now = now or datetime.now()
    send = send or _send_slack
    path = state_path(base)
    if not path.exists():
        return None
    with _Locked(base):
        state = _load(path)
        cleared = {k: state.pop(k) for k in list(kinds) if k in state}
        if not cleared:
            return None
        _save(path, state)
    told = {k: v for k, v in cleared.items() if v.get("notified")}
    if not told or not _enabled():
        return None
    lines = ["[house-alert] 直りました"]
    for kind, item in told.items():
        first = datetime.fromisoformat(item["first"])
        label = KIND_LABELS.get(kind, kind)
        lines.append(f"・{label}: {first.strftime('%m/%d %H:%M')} から {item.get('count', 0)} 回")
    where = _where(source, character)
    if where:
        lines.append(f"{now.strftime('%m/%d %H:%M')} {where} が成功")
    text = "\n".join(lines)
    try:
        return text if send(text) else None
    except Exception as e:
        print(f"[house-alert] 知らせを送れなかった: {type(e).__name__}", file=sys.stderr)
        return None


def check_result(base: Path, result: dict | None, source: str, character: str = "",
                 now: datetime | None = None, send: Callable[[str], bool] | None = None) -> str | None:
    """Claude の結果を見て、失敗なら覚えて知らせ、成功なら続いていた失敗を閉じる。"""
    kind, detail = classify(result)
    if kind is None:
        return ok(base, CLAUDE_KINDS, source, character, now, send)
    return report(base, kind, source, character, detail, now, send)


def main() -> int:
    parser = argparse.ArgumentParser(description="家の知らせ(失敗を世話人へ)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check-stream", help="Claude の stream.jsonl を見て、失敗なら知らせる")
    p.add_argument("--source", required=True)
    p.add_argument("--character", default="")
    p.add_argument("--stream", required=True, type=Path)

    p = sub.add_parser("report", help="失敗を 1 件知らせる")
    p.add_argument("--kind", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--character", default="")
    p.add_argument("--detail", default="")

    p = sub.add_parser("ok", help="うまくいった(続いていた失敗を閉じる)")
    p.add_argument("--kind", required=True)
    p.add_argument("--source", default="")
    p.add_argument("--character", default="")

    sub.add_parser("status", help="いま続いている失敗")

    args = parser.parse_args()
    base = data_dir()
    if args.cmd == "check-stream":
        text = check_result(base, read_result(args.stream), args.source, args.character)
    elif args.cmd == "report":
        text = report(base, args.kind, args.source, args.character, args.detail)
    elif args.cmd == "ok":
        text = ok(base, [args.kind], args.source, args.character)
    else:
        state = _load(state_path(base))
        if not state:
            print("続いている失敗はありません")
        for kind, item in state.items():
            print(f"{kind}: {item.get('first')} から {item.get('count')} 回 / 知らせ済み {item.get('notified') or 'まだ'}")
        return 0
    if text:
        print(f"[house-alert] 知らせた: {text.splitlines()[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
