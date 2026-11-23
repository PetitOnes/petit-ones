"""日記づくりの結果を見分ける: Claude の失敗の文を、日記として保存しないために。

2026-11-23 の夜、ぷち用のログインが切れていて、`claude --output-format json` の result に入った
「Failed to authenticate: …」が、そのまま 3 人の日記として保存された。
失敗は例外にして、呼ぶ側が「保存しない」と決められるようにする。
"""

from __future__ import annotations

import json

FAILED_PREFIX = "（サマリー生成失敗"


class DiaryFailed(RuntimeError):
    """日記の文を作れなかった。result は Claude の結果(あれば。家の知らせの見分けに使う)。"""

    def __init__(self, message: str, result: dict | None = None) -> None:
        super().__init__(message)
        self.result = result


def claude_text(raw: str, stderr: str = "") -> str:
    """`claude --output-format json` の出力から、日記の文を取り出す。失敗なら DiaryFailed。"""
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        result = None
    if not isinstance(result, dict):
        why = " ".join((stderr or raw or "").split())[:200]
        raise DiaryFailed(why or "Claude が何も返さなかった")
    text = str(result.get("result") or "").strip()
    if result.get("is_error"):
        raise DiaryFailed(text[:200] or str(result.get("subtype") or "Claude がエラーで終わった"), result)
    if not text:
        raise DiaryFailed("Claude が空の文を返した", result)
    return text


def failed_text(error: object) -> str:
    """画面に出す失敗の文(保存はしない)。"""
    return f"{FAILED_PREFIX}: {error}）"


def is_failed(summary: str | None) -> bool:
    """failed_text で作った文か。"""
    return bool(summary) and str(summary).startswith(FAILED_PREFIX)
