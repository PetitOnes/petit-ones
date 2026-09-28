#!/usr/bin/env python3
"""tmux pipe-pane の出力からClaudeの返答を抽出してchat_historyに保存する。

使い方:
  tmux pipe-pane -o -t SESSION:WINDOW "python3 /path/to/tmux_chat_capture.py --char-id puchiko"

標準入力から生のPTY出力を受け取り、ANSIコードを除去してClaudeの
テキスト返答だけを chat_history.json に保存する。
"""
import sys
import re
import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ANSIエスケープコードの除去パターン
ANSI = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;]*[mGKHFJABCDsuRLM]|\][^\x07]*\x07|[()][0-9a-zA-Z])')
# Claude Code UIのノイズパターン（ツール呼び出し・スピナー・プロンプト等）
NOISE = re.compile(
    r'^(\s*[●⏺⏻⏼✓✗✦✻✽✶✷✸✹❯❯❯⠀-⣿⠀-⣿])'  # ツール・スピナー記号
    r'|^\s*\[.*\]\s*$'       # [ツール名] 形式
    r'|^\s*↑|↓'              # トークンカウンタ
    r'|^\s*─{5,}'            # セパレータ
    r'|Waiting…|Hyperspacing|Running|stop'  # 待機メッセージ
    r'|^\s*$'                # 空行
    r'|^>?\s*$'              # プロンプト
    r'|bypasspermissions'    # bypass permissions表示
    r'|Claude Code'          # Claude Code UI要素
    r'|\$\s*\d+\.'           # コスト表示
    r'|tokens'               # トークン表示
)

DATA_DIR = Path("/home/cube-petit/petit_claude")
SCRIPTS_DIR = Path("/home/cube-petit/work/embodied-claude/scripts")

# 複数キャラの名前プレフィックスパターン
# 「**ぷちこ**: 」「**ぷちてゃ**: 」などのマルチキャラ形式
CHAR_PREFIX = re.compile(r'^\*\*(ぷちこ|ぷちてゃ|ぷちる)\*\*:\s*(.+)')
CHAR_ID_MAP = {"ぷちこ": "puchiko", "ぷちてゃ": "puchiteya", "ぷちる": "puchiru"}

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--char-id", dest="char_id", default="")
parser.add_argument("--multi", action="store_true", help="複数キャラモード（名前プレフィックスで判定）")
args, _ = parser.parse_known_args()

def save_message(char_id: str, text: str):
    if not char_id:
        return
    text = text.strip()
    if not text or len(text) < 3:
        return
    now = datetime.now(timezone.utc)
    now_jst = now.astimezone(timezone(timedelta(hours=9)))
    timestamp = now.isoformat()

    # chat_histories/chat_history.json
    p = DATA_DIR / "characters" / char_id / "chat_histories" / "chat_history.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        log = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except Exception:
        log = []
    # 直前のエントリと同じ内容なら重複スキップ
    if log and log[-1].get("role") == char_id and log[-1].get("text") == text:
        return
    log.append({"role": char_id, "text": text, "timestamp": timestamp})
    p.write_text(json.dumps(log[-200:], ensure_ascii=False, indent=2), encoding="utf-8")

    # .autonomous-logs テキストログ
    log_dir = DATA_DIR / ".autonomous-logs" / char_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"chat_{now_jst.strftime('%Y%m%d')}.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{now_jst.strftime('%Y-%m-%d %H:%M:%S')} JST] [{char_id}] {text}\n")


buf: list[str] = []
last_save_time = 0.0

def flush_buffer():
    global buf, last_save_time
    if not buf:
        return
    text = " ".join(buf).strip()
    buf = []
    if not text or len(text) < 5:
        return
    import time
    now = time.time()
    # multi モードは複数キャラが連続して返答するためクールダウンをスキップ
    if not args.multi and now - last_save_time < 1.0:
        return
    last_save_time = now
    save_message(args.char_id, text)


for raw_line in sys.stdin:
    # ANSIコードを除去
    line = ANSI.sub("", raw_line).rstrip()

    # ノイズ行をスキップ
    if NOISE.search(line):
        if buf:
            flush_buffer()
        continue

    if args.multi:
        # マルチキャラモード: 「**ぷちこ**: テキスト」形式を検出
        m = CHAR_PREFIX.match(line)
        if m:
            if buf:
                flush_buffer()
            char_name_ja = m.group(1)
            char_id = CHAR_ID_MAP.get(char_name_ja, args.char_id)
            args.char_id = char_id  # 動的に切り替え
            text = m.group(2).strip()
            if text:
                buf.append(text)
        elif args.char_id and line.strip():
            buf.append(line.strip())
    else:
        # 単一キャラモード
        if line.strip():
            buf.append(line.strip())
        else:
            flush_buffer()

# ストリーム終端で残バッファをフラッシュ
if buf:
    flush_buffer()
