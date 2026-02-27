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
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# main.py と同じパス解決
sys.path.insert(0, str(Path(__file__).parent))
from main import (
    CHARACTERS_DIR,
    _query_memories,
    char_dir,
    generate_diary_summary,
    list_characters,
)


async def generate_all(date: str) -> None:
    chars = list_characters()
    if not chars:
        print("キャラクターが見つかりません")
        return

    for char in chars:
        cid = char["id"]
        name = char.get("name", cid)
        memories = _query_memories(cid, 200, date_filter=date)
        if not memories:
            print(f"[{name}] {date}: 記憶なし — スキップ")
            continue

        print(f"[{name}] {date}: {len(memories)}件の記憶から日記生成中...")
        summary = await generate_diary_summary(cid, date, memories)

        # キャッシュ保存
        if summary:
            cache_dir = char_dir(cid) / "diary"
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"{date}.txt").write_text(summary, encoding="utf-8")
            print(f"[{name}] 保存完了: {summary[:60]}...")
        else:
            print(f"[{name}] 生成失敗")


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
