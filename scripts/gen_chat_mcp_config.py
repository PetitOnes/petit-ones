#!/usr/bin/env python3
"""チャット用に、指定キャラ専用のMCPサーバーだけへ絞り込んだ mcp-config を生成する。

.mcp.json には CHARACTER_ID 未設定の汎用サーバー（m5-mcp, memory, desire-system）も
同居しており、それを terminal chat から呼んでしまうと声や欲求がキャラ別ではなく
デフォルト（または desire-system は puchiko 固定）にすり替わる事故が起きる。
これを防ぐため、チャット起動時は各キャラの専用サーバーだけを --mcp-config で渡す。

Usage: gen_chat_mcp_config.py <char_id> [<char_id> ...] > /tmp/xxx.json
"""
import json
import sys
from pathlib import Path

MCP_JSON = Path(__file__).resolve().parent.parent / ".mcp.json"
PREFIXES = ("memory-", "m5-", "notes-", "relations-", "desire-system-")


def main():
    char_ids = sys.argv[1:]
    if not char_ids:
        print("Usage: gen_chat_mcp_config.py <char_id> [<char_id> ...]", file=sys.stderr)
        sys.exit(1)

    data = json.loads(MCP_JSON.read_text())
    servers = data.get("mcpServers", {})
    wanted_names = {f"{prefix}{char_id}" for prefix in PREFIXES for char_id in char_ids}
    filtered = {name: cfg for name, cfg in servers.items() if name in wanted_names}

    json.dump({"mcpServers": filtered}, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
