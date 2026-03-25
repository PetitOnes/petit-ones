#!/usr/bin/env python3
"""
インタラクティブセッション終了時に、ありさんと話した時刻を記録するスクリプト。
Stopフックから呼び出される。

環境変数 PETIT_CHARACTER_ID でキャラクターIDを指定（デフォルト: puchiko）
"""
import os
import sys
from datetime import datetime
from pathlib import Path

CHARACTER_ID = os.environ.get("PETIT_CHARACTER_ID", "puchiko")
SESSION_USER = os.environ.get("PETIT_SESSION_USER", "")
DATA_DIR = Path(os.environ.get("PETIT_DATA_DIR", Path.home() / "petit_claude"))
char_dir = DATA_DIR / "characters" / CHARACTER_ID
last_session_file = char_dir / "last_session.txt"

if not char_dir.exists():
    sys.exit(0)

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
line = f"{now} {SESSION_USER}".strip() + "\n"
last_session_file.write_text(line)
