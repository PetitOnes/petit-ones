#!/usr/bin/env python3
"""
stream-json 形式の Claude 出力を人間が読めるログに変換する。

使い方:
  claude -p ... --output-format stream-json 2>&1 | tee stream.jsonl | python3 format_stream_log.py >> out.log
  または
  python3 format_stream_log.py stream.jsonl >> out.log
"""
import sys
import json

MAX_TEXT = 2000   # テキスト出力の最大文字数
MAX_INPUT = 500   # ツール入力の最大文字数
MAX_RESULT = 800  # ツール結果の最大文字数


def truncate(s, n):
    s = s.strip()
    if len(s) > n:
        return s[:n] + f"…({len(s)-n}文字省略)"
    return s


def format_event(ev):
    lines = []
    t = ev.get("type", "")

    if t == "system" and ev.get("subtype") == "init":
        model = ev.get("model", "?")
        lines.append(f"[init] model={model}")

    elif t == "assistant":
        msg = ev.get("message", {})
        for block in msg.get("content", []):
            if block.get("type") == "text":
                text = truncate(block.get("text", ""), MAX_TEXT)
                if text:
                    lines.append(f"[Claude]\n{text}")
            elif block.get("type") == "tool_use":
                name = block.get("name", "?")
                inp = json.dumps(block.get("input", {}), ensure_ascii=False)
                inp = truncate(inp, MAX_INPUT)
                lines.append(f"[tool→] {name}\n  {inp}")

    elif t == "user":
        msg = ev.get("message", {})
        for block in msg.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result":
                content = block.get("content", [])
                if isinstance(content, str):
                    text = truncate(content, MAX_RESULT)
                    if text:
                        lines.append(f"[←tool]\n  {text}")
                elif isinstance(content, list):
                    for rb in content:
                        if isinstance(rb, dict) and rb.get("type") == "text":
                            text = truncate(rb.get("text", ""), MAX_RESULT)
                            if text:
                                lines.append(f"[←tool]\n  {text}")

    elif t == "result":
        subtype = ev.get("subtype", "")
        turns = ev.get("num_turns", "?")
        cost = ev.get("total_cost_usd", 0)
        lines.append(f"[result] subtype={subtype} turns={turns} cost=${cost:.4f}")
        # permission_denials
        denials = ev.get("permission_denials", [])
        if denials:
            lines.append(f"[denials] {len(denials)}件のツール拒否あり")
            for d in denials:
                lines.append(f"  拒否: {d.get('tool_name','?')}")

    return lines


def main():
    src = open(sys.argv[1]) if len(sys.argv) > 1 else sys.stdin
    for raw_line in src:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            ev = json.loads(raw_line)
        except json.JSONDecodeError:
            # JSONでない行はそのまま出力
            print(raw_line)
            continue
        for line in format_event(ev):
            print(line)
    if src is not sys.stdin:
        src.close()


if __name__ == "__main__":
    main()
