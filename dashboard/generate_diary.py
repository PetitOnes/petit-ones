#!/usr/bin/env python3
"""
一日の終わりに日記サマリーを生成してキャッシュするスクリプト。
cron で 23:50 に実行する想定。

Usage:
  uv run python generate_diary.py [date]
  # date省略時は今日
  # 例: uv run python generate_diary.py 2026-02-27
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# main.py と同じパス解決
sys.path.insert(0, str(Path(__file__).parent))
from main import (
    DATA_DIR,
    _diary_result,
    _query_memories,
    char_dir,
    generate_diary_summary,
    list_characters,
)


def update_diary_summary(cid: str, recent_days: int = 7) -> None:
    """diary/ 以下のファイルから diary_summary.md を生成・更新する。"""
    diary_dir = char_dir(cid) / "diary"
    if not diary_dir.exists():
        return

    files = sorted(diary_dir.glob("*.txt"), reverse=True)
    if not files:
        return

    latest_file = files[0]
    latest_date = latest_file.stem
    latest_text = latest_file.read_text(encoding="utf-8").strip()

    lines = [f"## 最新の日記（{latest_date}）\n", latest_text, ""]

    past_files = files[1: recent_days + 1]
    if past_files:
        lines.append("## 直近の日記")
        for f in past_files:
            text = f.read_text(encoding="utf-8").strip()
            first_line = text.splitlines()[0] if text else ""
            if len(first_line) > 80:
                first_line = first_line[:80] + "…"
            lines.append(f"- {f.stem}: {first_line}")

    summary_path = char_dir(cid) / "diary_summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def generate_all(date: str) -> None:
    chars = list_characters()
    if not chars:
        print("キャラクターが見つかりません")
        return

    failures: list[str] = []
    made = 0
    for char in chars:
        cid = char["id"]
        name = char.get("name", cid)
        memories = _query_memories(cid, 200, date_filter=date)
        if not memories:
            print(f"[{name}] {date}: 記憶なし — スキップ")
            continue

        print(f"[{name}] {date}: {len(memories)}件の記憶から日記生成中...")
        summary = await generate_diary_summary(cid, date, memories)

        # キャッシュ保存(作れなかったときの文は、日記として保存しない)
        if _diary_result().is_failed(summary):
            print(f"[{name}] 生成失敗(保存しない): {summary[:120]}")
            failures.append(summary)
        elif summary:
            cache_dir = char_dir(cid) / "diary"
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"{date}.txt").write_text(summary, encoding="utf-8")
            made += 1
            print(f"[{name}] 保存完了: {summary[:60]}...")
            update_diary_summary(cid)
            print(f"[{name}] diary_summary.md 更新完了")
        else:
            print(f"[{name}] 生成失敗")
    _tell_house(failures, made)


def _tell_house(failures: list[str], made: int) -> None:
    """作れなかった日記があれば世話人へ知らせ、作れたら続いていた知らせを閉じる(scripts/house_alert.py)。"""
    try:
        _diary_result()   # scripts/ を読めるようにする
        import house_alert
        if failures:
            kind, detail = house_alert.classify({"is_error": True, "result": failures[0]})
            house_alert.report(DATA_DIR, kind or "claude_error", "日記づくり", "", detail)
        elif made:
            house_alert.ok(DATA_DIR, house_alert.CLAUDE_KINDS, "日記づくり")
    except Exception as e:
        print(f"[house-alert] 知らせを送れなかった: {type(e).__name__}")


def main() -> None:
    if len(sys.argv) > 1:
        date = sys.argv[1]
    else:
        date = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")

    print(f"=== 日記生成: {date} ===")
    asyncio.run(generate_all(date))
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
