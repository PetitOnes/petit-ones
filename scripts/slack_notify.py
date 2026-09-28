#!/usr/bin/env python3
"""Slackの#099_embnodied-claudeに通知を送る（petitclaudeボットとして）。

Usage:
    python3 slack_notify.py "メッセージ"
    python3 slack_notify.py --channel C0XXXXXXX "メッセージ"

トークンは ~/petit_claude/.env の SLACK_APPROVE_BOT_TOKEN を使う。
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

ENV_FILE = Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude"))) / ".env"


def load_env_value(key: str) -> str | None:
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


def main() -> int:
    args = sys.argv[1:]
    channel = None
    if args and args[0] == "--channel" and len(args) >= 2:
        channel = args[1]
        args = args[2:]
    if not args:
        print(f"Usage: {sys.argv[0]} [--channel CXXXX] <message>", file=sys.stderr)
        return 1

    token = load_env_value("SLACK_APPROVE_BOT_TOKEN")
    channel = channel or load_env_value("SLACK_APPROVE_CHANNEL")
    if not token or not channel:
        print("Error: SLACK_APPROVE_BOT_TOKEN / SLACK_APPROVE_CHANNEL が .env にない", file=sys.stderr)
        return 1

    payload = json.dumps({"channel": channel, "text": " ".join(args)}).encode("utf-8")
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    if not result.get("ok"):
        print(f"Error: {result.get('error')}", file=sys.stderr)
        return 1
    print("送信しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
