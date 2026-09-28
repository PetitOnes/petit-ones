#!/usr/bin/env python3
"""PetitOnes / RRYZ09 のリポジトリへの「ありさん向けPR」をSlackに通知する。

「ありさん向け」の条件（いずれか）:
  - open PR の author が RRYZ09 以外（外部コントリビュータや別アカウントからのPR）
  - RRYZ09 にレビューリクエストが来ている

通知先: SLACK_GH_PR_CHANNEL（~/petit_claude/.env）。未設定時は SLACK_APPROVE_CHANNEL。
通知済みPRは state ファイルに記録して二重通知しない。closeされたら state から掃除。

cron想定: */15 * * * *
"""

import json
import subprocess
import sys
from pathlib import Path

SELF_LOGIN = "RRYZ09"
OWNERS = ["PetitOnes", "RRYZ09"]
# ありさんのアカウント（どちらかにレビューリクエストが来たら通知）
REVIEWER_LOGINS = ["RRYZ09", "AiriYokochi"]
STATE_FILE = Path.home() / "petit_claude" / "state" / "gh_pr_notified.json"
NOTIFY = Path.home() / "work" / "embodied-claude" / "scripts" / "slack_notify.py"
ENV_FILE = Path.home() / "petit_claude" / ".env"


def load_env_value(key: str) -> str | None:
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{key}="):
                return line.strip().split("=", 1)[1]
    except OSError:
        pass
    return None


def gh_json(args: list[str]):
    res = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}: {res.stderr.strip()[:200]}")
    return json.loads(res.stdout) if res.stdout.strip() else []


def open_prs_for_me() -> list[dict]:
    """全ownerのopen PRのうち、ありさん向けのものを返す。"""
    prs = []
    for owner in OWNERS:
        # orgでもuserでも同じsearch APIで拾える
        items = gh_json([
            "api", f"search/issues?q=is:pr+is:open+org:{owner}&per_page=50",
            "--jq", ".items",
        ])
        for it in items:
            author = (it.get("user") or {}).get("login", "")
            url = it.get("html_url", "")
            key = f"{url}"
            if author != SELF_LOGIN:
                prs.append({"key": key, "title": it.get("title", ""), "url": url,
                            "author": author, "reason": "外部からのPR"})
                continue
            # 自分作のPRでもレビューリクエストが来ていれば対象
            # (search APIはreview-requested修飾子で別途取得)
        for reviewer in REVIEWER_LOGINS:
            rr = gh_json([
                "api",
                f"search/issues?q=is:pr+is:open+org:{owner}+review-requested:{reviewer}&per_page=50",
                "--jq", ".items",
            ])
            for it in rr:
                url = it.get("html_url", "")
                prs.append({"key": url, "title": it.get("title", ""), "url": url,
                            "author": (it.get("user") or {}).get("login", ""),
                            "reason": f"レビューリクエスト → {reviewer}"})
    # 重複除去
    seen, out = set(), []
    for p in prs:
        if p["key"] not in seen:
            seen.add(p["key"])
            out.append(p)
    return out


def main() -> int:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        notified = set(json.loads(STATE_FILE.read_text()))
    except (OSError, ValueError):
        notified = set()

    try:
        prs = open_prs_for_me()
    except RuntimeError as e:
        print(f"取得失敗: {e}", file=sys.stderr)
        return 1

    open_keys = {p["key"] for p in prs}
    channel = load_env_value("SLACK_GH_PR_CHANNEL")
    for p in prs:
        if p["key"] in notified:
            continue
        msg = f"📬 PRが来ています（{p['reason']}） by {p['author']}\n{p['title']}\n{p['url']}"
        cmd = ["python3", str(NOTIFY)]
        if channel:
            cmd += ["--channel", channel]
        cmd.append(msg)
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            notified.add(p["key"])
            print(f"通知: {p['url']}")
        else:
            print(f"通知失敗: {res.stderr.strip()[:200]}", file=sys.stderr)

    # closeされたPRはstateから掃除（再openされたら再通知される）
    notified &= open_keys
    STATE_FILE.write_text(json.dumps(sorted(notified), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
