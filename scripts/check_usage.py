#!/usr/bin/env python3
"""Claude Code のトークン使用量を集計して表示する。

今日・今週・今月の input/output/cache トークン数を表示。

Usage:
    python3 check_usage.py                         # 全体
    python3 check_usage.py --character puchiteya   # キャラクター別
    python3 check_usage.py --json                  # JSON出力
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


def get_week_start(dt: datetime) -> datetime:
    monday = dt - timedelta(days=dt.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def load_session_ids(character: str) -> set[str]:
    """キャラクターのセッション履歴からセッションIDセットを返す。"""
    log_dir = Path.home() / "petit_claude" / ".autonomous-logs" / character
    history_file = log_dir / "session_history.txt"
    if not history_file.exists():
        return set()
    ids = set()
    for line in history_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            ids.add(line)
    return ids


def summarize(session_ids: set[str] | None = None) -> dict:
    """session_ids が None なら全体、指定すればそのセッションのみ集計。"""
    project_dir = Path.home() / ".claude" / "projects"
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = get_week_start(now)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    totals = {
        "today": {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0, "calls": 0},
        "week":  {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0, "calls": 0},
        "month": {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0, "calls": 0},
    }
    hourly = [0] * 24  # 今日の時間帯別呼び出し数（ローカル時刻）

    for jsonl_file in project_dir.glob("**/*.jsonl"):
        # キャラクター指定がある場合、セッションIDでフィルタ
        if session_ids is not None:
            file_session = jsonl_file.stem
            if file_session not in session_ids:
                continue

        try:
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    ts_str = d.get("timestamp")
                    msg = d.get("message")
                    if not ts_str or not isinstance(msg, dict):
                        continue
                    usage = msg.get("usage")
                    if not usage:
                        continue

                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except ValueError:
                        continue

                    inp = usage.get("input_tokens", 0)
                    out = usage.get("output_tokens", 0)
                    cc  = usage.get("cache_creation_input_tokens", 0)
                    cr  = usage.get("cache_read_input_tokens", 0)

                    for period, start in [("today", today_start), ("week", week_start), ("month", month_start)]:
                        if ts >= start:
                            totals[period]["input"]          += inp
                            totals[period]["output"]         += out
                            totals[period]["cache_creation"] += cc
                            totals[period]["cache_read"]     += cr
                            totals[period]["calls"]          += 1

                    if ts >= today_start:
                        local_ts = ts.astimezone()
                        hourly[local_ts.hour] += 1
        except Exception:
            continue

    totals["hourly"] = hourly
    return totals


def fmt_k(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    character = None
    if "--character" in args:
        idx = args.index("--character")
        if idx + 1 < len(args):
            character = args[idx + 1]

    session_ids = None
    if character:
        session_ids = load_session_ids(character)

    data = summarize(session_ids)

    if as_json:
        out = {"character": character or "all", "usage": data}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    now = datetime.now(timezone.utc).astimezone()
    week_start = get_week_start(datetime.now(timezone.utc)).astimezone()
    label = character if character else "全体"
    print(f"Claude Code 使用量 [{label}]  ({now.strftime('%Y-%m-%d %H:%M %Z')})")
    if character and session_ids is not None:
        print(f"  セッション数（累計）: {len(session_ids)}")
    print()
    for period, plabel in [("today", "今日"), ("week", f"今週 ({week_start.strftime('%m/%d')}〜)"), ("month", f"今月 ({now.strftime('%m')}月)")]:
        t = data[period]
        total_input = t["input"] + t["cache_creation"] + t["cache_read"]
        print(f"【{plabel}】  {t['calls']} calls")
        print(f"  input:  {fmt_k(t['input'])} (cache作成: {fmt_k(t['cache_creation'])}, cache読取: {fmt_k(t['cache_read'])})")
        print(f"  output: {fmt_k(t['output'])}")
        print(f"  合計input換算: {fmt_k(total_input)}")
        print()

    # 今日の時間帯分布
    hourly = data.get("hourly", [])
    if any(hourly):
        print("【今日の時間帯別呼び出し数】")
        max_calls = max(hourly)
        bar_max = 20
        for h, c in enumerate(hourly):
            if c == 0:
                continue
            bar = "#" * (c * bar_max // max_calls) if max_calls > 0 else ""
            print(f"  {h:02d}時: {bar} {c}")


if __name__ == "__main__":
    main()
