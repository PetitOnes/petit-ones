"""
Desire System MCP Server - プチの自発的な欲求レベルを提供する。

desires.json（desire_updater.pyが定期更新）を読み込み、
現在の欲求状態をMCPツール経由で返す。
欲求定義は desire_config.json から動的に読み込む。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from desire_updater import (
    CHARACTER_ID,
    DESIRES_PATH,
    DesireSystemConfig,
    load_desire_config,
)

server = Server("desire-system")


def _load_config() -> DesireSystemConfig | None:
    """desire_config.json を読み込む。失敗時は None。"""
    try:
        return load_desire_config(CHARACTER_ID)
    except FileNotFoundError:
        return None


def _get_labels() -> dict[str, str]:
    """欲求の日本語ラベルを desire_config.json から取得。"""
    config = _load_config()
    if config is None:
        return {}
    return {did: d.name_ja for did, d in config.desires.items()}


def load_desires() -> dict[str, Any] | None:
    """desires.json を読み込む。存在しなければ None。"""
    if not DESIRES_PATH.exists():
        return None
    try:
        with open(DESIRES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_labels_from_data(data: dict[str, Any]) -> dict[str, str]:
    """desires.json または config からラベルを取得。"""
    labels = data.get("labels", {})
    if labels:
        return labels
    return _get_labels()


def format_desires(data: dict[str, Any]) -> str:
    """欲求データを読みやすい形式に整形する。"""
    lines = []
    dominant = data.get("dominant", "")
    desires = data.get("desires", {})
    updated_at = data.get("updated_at", "")
    labels = get_labels_from_data(data)

    # dominant欲求
    dominant_label = labels.get(dominant, dominant)
    lines.append(f"【最も強い欲求】{dominant_label} (level: {desires.get(dominant, 0):.3f})")
    lines.append("")

    # 全欲求レベル
    lines.append("【欲求レベル一覧】")
    for key, level in sorted(desires.items(), key=lambda x: -x[1]):
        label = labels.get(key, key)
        bar = "\u2588" * int(level * 10) + "\u2591" * (10 - int(level * 10))
        lines.append(f"  {label}: [{bar}] {level:.3f}")

    # センサー情報
    sensor = data.get("sensor_snapshot", {})
    if sensor:
        lines.append("")
        lines.append("【センサー】")
        for k, v in sensor.items():
            lines.append(f"  {k}: {v}")

    if updated_at:
        lines.append(f"\n更新: {updated_at}")

    return "\n".join(lines)


def _build_desire_action_description() -> str:
    """キャラ固有の欲求名と行動マッピングをツール説明文に自動生成。"""
    config = _load_config()
    if config is None:
        return (
            "Get current desire levels. "
            "Act immediately on any desire with level >= 0.7."
        )

    parts = ["Get current desire levels. "]
    parts.append("IMPORTANT: Act immediately on any desire with level >= 0.7. ")

    for did, d in config.desires.items():
        parts.append(f"{did}({d.name_ja}): {d.description}; ")

    parts.append(
        "After acting, call satisfy_desire to record satisfaction. "
        "Keep acting until level drops below 0.5. "
        "Desires drive behavior - do not just report them."
    )
    return "".join(parts)


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    config = _load_config()
    desire_names = list(config.desires.keys()) if config else []
    desire_names_str = ", ".join(desire_names) if desire_names else "（desire_config.json を確認）"

    return [
        Tool(
            name="get_desires",
            description=_build_desire_action_description(),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="satisfy_desire",
            description=(
                "Satisfy a desire after taking an action. "
                "Pass the desire_name you just acted on. "
                "The level drops by 0.4. Call again if still high."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "desire_name": {
                        "type": "string",
                        "description": f"Name of the desire to satisfy: {desire_names_str}",
                    },
                },
                "required": ["desire_name"],
            },
        ),
        Tool(
            name="boost_desire",
            description=(
                "Boost a desire level due to novelty/surprise (dopamine/prediction error). "
                "Call when you feel surprised or encounter unexpected info. "
                "Simulates dopamine response to novelty."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "desire_name": {
                        "type": "string",
                        "description": f"Name of the desire to boost: {desire_names_str}",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Amount to boost (0.1-0.5). 0.2=mild surprise, 0.5=strong.",
                    },
                },
                "required": ["desire_name", "amount"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    labels = _get_labels()

    if name == "get_desires":
        data = load_desires()
        if data is None:
            return [TextContent(
                type="text",
                text=(
                    "desires.jsonが見つからへん。\n"
                    f"パス: {DESIRES_PATH}\n"
                    "desire_updater を先に実行: "
                    "uv run --directory desire-system desire-updater"
                ),
            )]
        return [TextContent(type="text", text=format_desires(data))]

    if name == "satisfy_desire":
        desire_name = arguments.get("desire_name", "")
        data = load_desires()
        if data is None:
            return [TextContent(
                type="text",
                text="desires.jsonが見つからへん。先にdesire-updaterを実行して。",
            )]

        desires = data.get("desires", {})
        if desire_name not in desires:
            valid = list(desires.keys())
            return [TextContent(type="text", text=f"欲求名が不正: {desire_name}. 有効: {valid}")]

        desires[desire_name] = max(0.0, desires[desire_name] - 0.4)
        dominant = max(desires, key=lambda k: desires[k])
        data["desires"] = desires
        data["dominant"] = dominant

        DESIRES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DESIRES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        label = labels.get(desire_name, desire_name)
        return [TextContent(
            type="text",
            text=(
                f"[満足] {label} -{0.4:.1f} → {desires[desire_name]:.3f}"
                f"\n\n{format_desires(data)}"
            ),
        )]

    if name == "boost_desire":
        desire_name = arguments.get("desire_name", "")
        amount = float(arguments.get("amount", 0.2))
        amount = max(0.0, min(0.5, amount))

        data = load_desires()
        if data is None:
            return [TextContent(
                type="text",
                text="desires.jsonが見つからへん。先にdesire-updaterを実行して。",
            )]

        desires = data.get("desires", {})
        if desire_name not in desires:
            valid = list(desires.keys())
            return [TextContent(type="text", text=f"欲求名が不正: {desire_name}. 有効: {valid}")]

        desires[desire_name] = min(1.0, desires[desire_name] + amount)
        dominant = max(desires, key=lambda k: desires[k])
        data["desires"] = desires
        data["dominant"] = dominant

        DESIRES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DESIRES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        label = labels.get(desire_name, desire_name)
        return [TextContent(
            type="text",
            text=f"[ドーパミン] {label} +{amount:.1f} → {desires[desire_name]:.3f}",
        )]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def run_server() -> None:
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Entry point."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
