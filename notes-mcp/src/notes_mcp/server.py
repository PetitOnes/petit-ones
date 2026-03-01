"""
Notes MCP Server - プチのメモ帳。

記憶は「思い出す」もの。メモ帳は「見返す」もの。
開けばすぐ見える場所にある、永続的なノート。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ノート保存先
_data_dir = Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))
_char_id = os.getenv("CHARACTER_ID", "puchiko")
NOTES_DIR = Path(os.getenv("NOTES_DIR", str(_data_dir / "characters" / _char_id / "notes")))

server = Server("notes")


def _ensure_dir() -> None:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)


def _safe_name(name: str) -> str:
    """ファイル名を安全にする。.md 拡張子を付ける。"""
    name = name.strip().replace("/", "_").replace("\\", "_").replace("..", "_")
    if not name:
        name = "untitled"
    if not name.endswith(".md"):
        name += ".md"
    return name


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_notes",
            description=(
                "List all notes in the notebook. "
                "Returns note names and their sizes. "
                "Use this to see what notes you have."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="read_note",
            description=(
                "Read a note by name. Returns the full content. "
                "Use this to look back at something you wrote down."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Note name (e.g. 'light_values' or 'light_values.md')",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="write_note",
            description=(
                "Write or update a note. Creates a new note or overwrites an existing one. "
                "Use markdown format. Good for reference tables, lists, research summaries, "
                "anything you want to look back at without searching memories."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Note name (e.g. 'light_values' or 'favorite_sounds')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full content of the note (markdown)",
                    },
                },
                "required": ["name", "content"],
            },
        ),
        Tool(
            name="append_note",
            description=(
                "Append text to an existing note. "
                "If the note doesn't exist, creates it. "
                "Use this to add entries to a list or log without rewriting the whole note."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Note name",
                    },
                    "content": {
                        "type": "string",
                        "description": "Text to append",
                    },
                },
                "required": ["name", "content"],
            },
        ),
        Tool(
            name="delete_note",
            description="Delete a note by name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Note name to delete",
                    },
                },
                "required": ["name"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    _ensure_dir()

    if name == "list_notes":
        files = sorted(NOTES_DIR.glob("*.md"))
        if not files:
            return [TextContent(
                type="text", text="メモ帳は空です。write_note で最初のノートを作ろう。",
            )]
        lines = ["【メモ帳一覧】"]
        for f in files:
            size = f.stat().st_size
            lines.append(f"  {f.stem} ({size} bytes)")
        lines.append(f"\n全 {len(files)} ノート")
        return [TextContent(type="text", text="\n".join(lines))]

    if name == "read_note":
        note_name = _safe_name(arguments.get("name", ""))
        path = NOTES_DIR / note_name
        if not path.exists():
            return [TextContent(type="text", text=f"ノートが見つかりません: {note_name}")]
        content = path.read_text(encoding="utf-8")
        return [TextContent(type="text", text=f"【{path.stem}】\n\n{content}")]

    if name == "write_note":
        note_name = _safe_name(arguments.get("name", ""))
        content = arguments.get("content", "")
        path = NOTES_DIR / note_name
        existed = path.exists()
        path.write_text(content, encoding="utf-8")
        action = "更新" if existed else "作成"
        return [TextContent(type="text", text=f"[{action}] {path.stem} ({len(content)} bytes)")]

    if name == "append_note":
        note_name = _safe_name(arguments.get("name", ""))
        content = arguments.get("content", "")
        path = NOTES_DIR / note_name
        existed = path.exists()
        with open(path, "a", encoding="utf-8") as f:
            if existed:
                f.write("\n")
            f.write(content)
        action = "追記" if existed else "作成"
        return [TextContent(type="text", text=f"[{action}] {path.stem}")]

    if name == "delete_note":
        note_name = _safe_name(arguments.get("name", ""))
        path = NOTES_DIR / note_name
        if not path.exists():
            return [TextContent(type="text", text=f"ノートが見つかりません: {note_name}")]
        path.unlink()
        return [TextContent(type="text", text=f"[削除] {path.stem}")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def run_server() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
