#!/usr/bin/env python3
"""
autonomous-action の stream-json ログを読みやすく表示する。

使い方:
  python3 read_stream.py <stream.jsonl>
  python3 read_stream.py <stream.jsonl> --no-thinking    # thinking省略
  python3 read_stream.py <stream.jsonl> --no-tool-result # ツール結果省略
  python3 read_stream.py <stream.jsonl> --json           # JSON出力（ダッシュボード用）

最新ファイルを自動選択:
  python3 read_stream.py puchiteya          # キャラ名だけで最新ファイル
  python3 read_stream.py puchiteya --last 3 # 最新3件を連結
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DATA_DIR = Path(os.environ.get("PETIT_DATA_DIR", Path.home() / "petit_claude"))
LOG_ROOT = DATA_DIR / ".autonomous-logs"

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
MAGENTA = "\033[35m"
RED = "\033[31m"
BLUE = "\033[34m"
GRAY = "\033[90m"


def trunc(s: str, n: int) -> str:
    s = s.strip()
    if len(s) > n:
        return s[:n] + f"\n  …({len(s) - n}文字省略)"
    return s


def fmt_tool_input(inp: dict) -> str:
    try:
        s = json.dumps(inp, ensure_ascii=False, indent=None)
        # command は特別扱い（長い場合が多い）
        if "command" in inp:
            cmd = inp["command"]
            rest = {k: v for k, v in inp.items() if k != "command"}
            parts = [f"command: {trunc(cmd, 300)}"]
            if rest:
                parts.append(json.dumps(rest, ensure_ascii=False))
            return "\n    ".join(parts)
        return trunc(s, 400)
    except Exception:
        return str(inp)[:400]


def fmt_tool_result(content) -> str:
    if isinstance(content, str):
        return trunc(content, 600)
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(trunc(block.get("text", ""), 600))
                elif block.get("type") == "tool_reference":
                    parts.append(f"[tool_reference: {block.get('tool_name', '?')}]")
        return "\n    ".join(parts) if parts else ""
    return str(content)[:600]


def parse_events(path: Path) -> list[dict]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


def render_text(events: list[dict], show_thinking: bool, show_tool_result: bool) -> str:
    lines = []
    tool_names: dict[str, str] = {}  # id → name

    for ev in events:
        t = ev.get("type", "")

        if t == "system" and ev.get("subtype") == "init":
            model = ev.get("model", "?")
            sid = ev.get("session_id", "?")
            lines.append(f"{DIM}{'─'*60}{RESET}")
            lines.append(f"{BOLD}[init]{RESET} model={model}")
            lines.append(f"{DIM}session={sid}{RESET}")

        elif t == "assistant":
            msg = ev.get("message", {})
            for block in msg.get("content", []):
                btype = block.get("type", "")
                if btype == "thinking":
                    if show_thinking:
                        thinking = block.get("thinking", "").strip()
                        lines.append(f"\n{MAGENTA}{'─'*4} 思考 {'─'*50}{RESET}")
                        lines.append(f"{DIM}{thinking}{RESET}")
                elif btype == "text":
                    text = block.get("text", "").strip()
                    if text:
                        lines.append(f"\n{BOLD}{GREEN}[Claude]{RESET}")
                        lines.append(text)
                elif btype == "tool_use":
                    tid = block.get("id", "")
                    name = block.get("name", "?")
                    tool_names[tid] = name
                    inp = block.get("input", {})
                    lines.append(f"\n{BOLD}{CYAN}[→ {name}]{RESET}")
                    lines.append(f"  {fmt_tool_input(inp)}")

        elif t == "user":
            msg = ev.get("message", {})
            for block in msg.get("content", []):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result" and show_tool_result:
                    tid = block.get("tool_use_id", "")
                    name = tool_names.get(tid, "?")
                    is_error = block.get("is_error", False)
                    content = fmt_tool_result(block.get("content", ""))
                    if content:
                        label = f"{RED}[← {name} ERROR]{RESET}" if is_error else f"{YELLOW}[← {name}]{RESET}"
                        lines.append(f"  {label}")
                        lines.append(f"  {GRAY}{content}{RESET}")

        elif t == "result":
            subtype = ev.get("subtype", "?")
            turns = ev.get("num_turns", "?")
            cost = ev.get("total_cost_usd", 0)
            result_text = ev.get("result", "")
            usage = ev.get("usage", {})
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            cc = usage.get("cache_creation_input_tokens", 0)
            cr = usage.get("cache_read_input_tokens", 0)
            denials = ev.get("permission_denials", [])

            lines.append(f"\n{DIM}{'─'*60}{RESET}")
            color = RED if "error" in subtype else GREEN
            lines.append(f"{BOLD}{color}[result]{RESET} {subtype} | turns={turns} | cost=${cost:.4f}")
            lines.append(f"  tokens: input={inp} output={out} cache_create={cc} cache_read={cr}")
            if denials:
                lines.append(f"  {RED}権限拒否: {len(denials)}件{RESET}")
                for d in denials:
                    lines.append(f"    ✗ {d.get('tool_name','?')}")
            if result_text:
                lines.append(f"\n{BOLD}[最終返答]{RESET}")
                lines.append(result_text.strip())

    return "\n".join(lines)


def render_json(events: list[dict]) -> list[dict]:
    """ダッシュボード用のJSON形式に変換"""
    out = []
    tool_names: dict[str, str] = {}

    for ev in events:
        t = ev.get("type", "")

        if t == "system" and ev.get("subtype") == "init":
            out.append({"kind": "init", "model": ev.get("model"), "session_id": ev.get("session_id")})

        elif t == "assistant":
            for block in ev.get("message", {}).get("content", []):
                btype = block.get("type", "")
                if btype == "thinking":
                    out.append({"kind": "thinking", "text": block.get("thinking", "")})
                elif btype == "text":
                    text = block.get("text", "").strip()
                    if text:
                        out.append({"kind": "text", "text": text})
                elif btype == "tool_use":
                    tid = block.get("id", "")
                    name = block.get("name", "?")
                    tool_names[tid] = name
                    out.append({"kind": "tool_call", "id": tid, "name": name, "input": block.get("input", {})})

        elif t == "user":
            for block in ev.get("message", {}).get("content", []):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    tid = block.get("tool_use_id", "")
                    name = tool_names.get(tid, "?")
                    content = block.get("content", "")
                    if isinstance(content, list):
                        text = "\n".join(
                            b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    else:
                        text = str(content)
                    out.append({
                        "kind": "tool_result",
                        "id": tid,
                        "name": name,
                        "text": text,
                        "is_error": block.get("is_error", False),
                    })

        elif t == "result":
            usage = ev.get("usage", {})
            out.append({
                "kind": "result",
                "subtype": ev.get("subtype"),
                "turns": ev.get("num_turns"),
                "cost_usd": ev.get("total_cost_usd", 0),
                "result": ev.get("result", ""),
                "usage": {
                    "input": usage.get("input_tokens", 0),
                    "output": usage.get("output_tokens", 0),
                    "cache_creation": usage.get("cache_creation_input_tokens", 0),
                    "cache_read": usage.get("cache_read_input_tokens", 0),
                },
                "permission_denials": [d.get("tool_name") for d in ev.get("permission_denials", [])],
            })

    return out


def resolve_path(arg: str, last: int = 1) -> list[Path]:
    p = Path(arg)
    if p.exists():
        return [p]
    # キャラ名として解釈
    char_dir = LOG_ROOT / arg
    if char_dir.is_dir():
        files = sorted(char_dir.glob("*_stream.jsonl"))
        return files[-last:] if files else []
    return []


def main() -> None:
    args = sys.argv[1:]
    show_thinking = "--no-thinking" not in args
    show_tool_result = "--no-tool-result" not in args
    as_json = "--json" in args
    last = 1
    if "--last" in args:
        idx = args.index("--last")
        last = int(args[idx + 1]) if idx + 1 < len(args) else 1

    positional = [a for a in args if not a.startswith("--") and not a.lstrip("-").isdigit()]
    if not positional:
        print("使い方: read_stream.py <stream.jsonl or キャラ名> [--no-thinking] [--no-tool-result] [--last N] [--json]")
        sys.exit(1)

    paths = resolve_path(positional[0], last)
    if not paths:
        print(f"ファイルが見つかりません: {positional[0]}", file=sys.stderr)
        sys.exit(1)

    if as_json:
        result = []
        for path in paths:
            evs = parse_events(path)
            result.append({"file": path.name, "events": render_json(evs)})
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for path in paths:
            print(f"\n{BOLD}{'='*60}{RESET}")
            print(f"{BOLD}{path.name}{RESET}")
            print(f"{BOLD}{'='*60}{RESET}")
            evs = parse_events(path)
            print(render_text(evs, show_thinking, show_tool_result))


if __name__ == "__main__":
    main()
