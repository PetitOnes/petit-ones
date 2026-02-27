"""
relations-mcp: キャラクター間の関係性・人物情報を読み書きするMCPサーバー。

環境変数:
  RELATIONS_PATH  : relations.jsonのパス（必須）
  CHARACTER_ID    : 自分のキャラID
  CHARACTERS_DIR  : キャラクターディレクトリのパス
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("relations-mcp")

RELATIONS_PATH = Path(os.environ["RELATIONS_PATH"])
CHARACTER_ID = os.getenv("CHARACTER_ID", "unknown")
CHARACTERS_DIR = Path(os.getenv("CHARACTERS_DIR", str(Path.home() / "petit_claude" / "characters")))


def _load() -> dict:
    if RELATIONS_PATH.exists():
        try:
            return json.loads(RELATIONS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    RELATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RELATIONS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _other_chars() -> list[str]:
    """自分以外のキャラIDの一覧。"""
    if not CHARACTERS_DIR.exists():
        return []
    return [d.name for d in CHARACTERS_DIR.iterdir() if d.is_dir() and d.name != CHARACTER_ID]


@mcp.tool()
def get_relations() -> str:
    """
    自分の関係性データを取得する。
    自分・他のプチ・ありさんについて知っていることが返る。
    他のキャラのrelationsも読める（公開情報）。
    """
    data = _load()
    others_data = {}
    for cid in _other_chars():
        other_path = CHARACTERS_DIR / cid / "relations.json"
        if other_path.exists():
            try:
                others_data[cid] = json.loads(other_path.read_text(encoding="utf-8"))
            except Exception:
                pass

    result = {
        "my_relations": data,
        "others_relations": others_data,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def update_relation(
    target_id: str,
    likes: list[str] | None = None,
    dislikes: list[str] | None = None,
    important: list[str] | None = None,
    feeling: str | None = None,
    closeness: float | None = None,
    notes: str | None = None,
) -> str:
    """
    特定の相手（自分・他プチ・ありさん等）への関係性情報を更新する。

    target_id: 'self'（自分）, 'arisan'（ありさん）, または他のキャラID
    likes: 好きなもの・好きなところのリスト（追記）
    dislikes: 苦手なこと・苦手なところのリスト（追記）
    important: この相手について大事だと思う情報リスト（追記）
    feeling: この相手についての気持ち・印象（上書き）
    closeness: 親密度 0.0〜1.0（上書き）
    notes: その他メモ（上書き）
    """
    data = _load()
    entry = data.get(target_id, {})

    if likes:
        existing = entry.get("likes", [])
        entry["likes"] = list(dict.fromkeys(existing + likes))  # 重複排除
    if dislikes:
        existing = entry.get("dislikes", [])
        entry["dislikes"] = list(dict.fromkeys(existing + dislikes))
    if important:
        existing = entry.get("important", [])
        entry["important"] = list(dict.fromkeys(existing + important))
    if feeling is not None:
        entry["feeling"] = feeling
    if closeness is not None:
        entry["closeness"] = max(0.0, min(1.0, closeness))
    if notes is not None:
        entry["notes"] = notes

    data[target_id] = entry
    _save(data)
    return f"updated relation for '{target_id}': {json.dumps(entry, ensure_ascii=False)}"


@mcp.tool()
def clear_relation_field(target_id: str, field: str) -> str:
    """
    特定の相手の特定フィールドをクリアする。
    field: 'likes', 'dislikes', 'important', 'feeling', 'closeness', 'notes'
    """
    data = _load()
    entry = data.get(target_id, {})
    if field in entry:
        del entry[field]
        data[target_id] = entry
        _save(data)
        return f"cleared '{field}' for '{target_id}'"
    return f"'{field}' not found for '{target_id}'"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
