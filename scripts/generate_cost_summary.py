#!/usr/bin/env python3
"""コストサマリーを ~/petit_claude/cost_summary.md に書き出す。

cron で定期実行して、キャラクターが Bash cat で読めるようにする。
"""

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
TOKEN_LOG = Path.home() / "petit_claude" / "token_logs" / "token_log.jsonl"
SUMMARY_DIR = Path.home() / "petit_claude" / "cost_summary"
BUDGET = 200.0
RESET_DAY = 26


def load_entries():
    if not TOKEN_LOG.exists():
        return []
    entries = []
    with TOKEN_LOG.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                ts_raw = ev.get("timestamp", "")
                if not ts_raw:
                    continue
                dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                dt_jst = dt.astimezone(JST)
                date_str = dt_jst.strftime("%Y-%m-%d")
                cost = ev.get("cost_usd") or 0
                if cost == 0:
                    ci = ev.get("input", 0) or 0
                    co = ev.get("output", 0) or 0
                    cc = ev.get("cache_creation", 0) or 0
                    cr = ev.get("cache_read", 0) or 0
                    cost = (ci * 3 + co * 15 + cc * 3.75 + cr * 0.30) / 1e6
                entries.append({
                    "date": date_str,
                    "character": ev.get("character", "unknown"),
                    "source": ev.get("source", "unknown"),
                    "cost": cost,
                })
            except Exception:
                pass
    return entries


def calc_cycle(now):
    if now.day >= RESET_DAY:
        start = now.replace(day=RESET_DAY, hour=0, minute=0, second=0, microsecond=0)
        nm = now.month + 1 if now.month < 12 else 1
        ny = now.year if now.month < 12 else now.year + 1
        end = now.replace(year=ny, month=nm, day=RESET_DAY, hour=0, minute=0, second=0, microsecond=0)
    else:
        end = now.replace(day=RESET_DAY, hour=0, minute=0, second=0, microsecond=0)
        pm = now.month - 1 if now.month > 1 else 12
        py = now.year if now.month > 1 else now.year - 1
        start = now.replace(year=py, month=pm, day=RESET_DAY, hour=0, minute=0, second=0, microsecond=0)
    return start, end


def main():
    now = datetime.now(JST)
    today_str = now.strftime("%Y-%m-%d")
    entries = load_entries()

    def cost_sum(lst):
        return sum(e.get("cost", 0) for e in lst)

    today_e = [e for e in entries if e.get("date") == today_str]
    today_cost = cost_sum(today_e)

    cycle_start, cycle_end = calc_cycle(now)
    cs = cycle_start.strftime("%Y-%m-%d")
    ce = cycle_end.strftime("%Y-%m-%d")
    cycle_e = [e for e in entries if cs <= e.get("date", "") < ce]
    cycle_cost = cost_sum(cycle_e)

    days_elapsed = (now.date() - cycle_start.date()).days
    cycle_days = (cycle_end.date() - cycle_start.date()).days
    ideal = BUDGET * days_elapsed / max(cycle_days, 1)
    remaining = max(0, BUDGET - cycle_cost)
    days_remaining = (cycle_end.date() - now.date()).days

    # キャラ別・ソース別（サイクル内）
    by_char = {}
    by_src = {}
    for e in cycle_e:
        c = e.get("character", "unknown")
        s = e.get("source", "unknown")
        by_char[c] = by_char.get(c, 0) + e.get("cost", 0)
        by_src[s] = by_src.get(s, 0) + e.get("cost", 0)

    # 日別（サイクル全日付）
    daily = {}
    cur = cycle_start.date()
    end_date = now.date()
    while cur <= end_date:
        d_str = cur.strftime("%Y-%m-%d")
        day_e = [e for e in entries if e["date"] == d_str]
        daily[d_str] = sum(e["cost"] for e in day_e)
        cur += timedelta(days=1)

    lines = [
        f"# コストサマリー（{now.strftime('%Y-%m-%d %H:%M')} JST 更新）",
        "",
        f"- **今日**: ${today_cost:.3f}",
        f"- **今月合計** ({cs}〜{ce}): ${cycle_cost:.3f}",
        f"- **理想値** (今日まで): ${ideal:.2f}",
        f"- **残り予算**: ${remaining:.2f}（残り{days_remaining}日）",
        f"- **月額上限**: ${BUDGET:.0f}",
        "",
        "## キャラクター別（今月）",
    ]
    for char, cost in sorted(by_char.items(), key=lambda x: -x[1]):
        lines.append(f"- {char}: ${cost:.3f}")

    lines += ["", "## ソース別（今月）"]
    src_labels = {"autonomous": "自律行動", "chat": "チャット", "sensor": "センサー", "camera": "カメラ", "mic": "マイク"}
    for src, cost in sorted(by_src.items(), key=lambda x: -x[1]):
        label = src_labels.get(src, src)
        lines.append(f"- {label}: ${cost:.3f}")

    lines += ["", "## 日別（今月サイクル）"]
    for d_str, cost in sorted(daily.items()):
        marker = " ← 今日" if d_str == today_str else ""
        lines.append(f"- {d_str}: ${cost:.3f}{marker}")

    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    out_file = SUMMARY_DIR / f"{cs}.md"
    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written: {out_file}")


if __name__ == "__main__":
    main()
