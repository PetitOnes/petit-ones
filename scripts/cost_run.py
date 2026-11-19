#!/usr/bin/env python3
"""claude の 1 回ぶんの代を、記録のときに出す。

`claude --resume` の result.total_cost_usd は、セッションの累計で返る(2026-09 から)。これまでは token_log.jsonl に
累計をそのまま書き、読むときに cost_correct.py で推定して直していた。ここでは、セッション id ごとに前に見た累計を
覚えておき、差(= 1 回ぶん)を cost_run として一緒に書く(2026-11-19 ありさん)。

置き場所: PETIT_DATA_DIR/token_logs/session_totals.json  {"<session_id>": {"total": 1.23, "at": "…"}}(14 日より古い分は捨てる)

Usage(シェルから):
    python3 cost_run.py <session_id> <total_cost_usd>   # 1 回ぶんを 1 行で出す(覚えた累計も更新する)
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

KEEP_DAYS = 14


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))


def run_cost(session_id: str, total: float, base: Path | None = None, now: datetime | None = None) -> float:
    """このセッションで前に見た累計との差。はじめて見るセッションなら total のまま。累計が減っていたら(別物)total"""
    total = float(total or 0)
    if not session_id:
        return total
    path = (base or data_dir()) / "token_logs" / "session_totals.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now()
    with open(path.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            seen = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(seen, dict):
                seen = {}
        except (OSError, json.JSONDecodeError):
            seen = {}
        prev = float((seen.get(session_id) or {}).get("total", 0) or 0)
        cost = total - prev if 0 < prev <= total else total
        seen[session_id] = {"total": total, "at": now.isoformat(timespec="seconds")}
        cut = (now - timedelta(days=KEEP_DAYS)).isoformat(timespec="seconds")
        seen = {k: v for k, v in seen.items() if isinstance(v, dict) and str(v.get("at", "")) >= cut}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(seen) + "\n", encoding="utf-8")
        tmp.replace(path)
    return round(cost, 6)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        total = float(argv[1])
    except ValueError:
        total = 0.0
    print(run_cost(argv[0], total))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
