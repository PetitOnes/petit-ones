#!/usr/bin/env python3
"""ノートエントリ書き込みスクリプト"""
import json
import sys
import os

notebook_path = '/home/cube-petit/petit_claude/chat_history/exchange_notebook.json'
content_file = os.path.join(os.path.dirname(__file__), 'notebook_content.txt')

author = sys.argv[1] if len(sys.argv) > 1 else 'ぷちこ'
date = sys.argv[2] if len(sys.argv) > 2 else '2026/03/25 12:46'

with open(content_file, encoding='utf-8') as f:
    content = f.read().strip()

with open(notebook_path, encoding='utf-8') as f:
    data = json.load(f)

entry = {
    'author': author,
    'date': date,
    'content': content
}

data.append(entry)
with open(notebook_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f'wrote ok: {author} at {date}')
