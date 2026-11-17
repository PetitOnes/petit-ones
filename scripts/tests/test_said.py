"""said.py: 言った言葉を集めて探す"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import said  # noqa: E402


def _stream(path: Path, blocks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    msg = {"type": "assistant", "message": {"content": [dict(type="tool_use", **b) for b in blocks]}}
    path.write_text(json.dumps(msg, ensure_ascii=False) + "\n", encoding="utf-8")


def _house(tmp_path: Path) -> Path:
    logs = tmp_path / ".autonomous-logs" / "ko"
    _stream(logs / "20261117_100000_stream.jsonl", [
        {"name": "mcp__m5-mcp__speak", "input": {"text": "窓の外が白い"}},
        {"name": "Bash", "input": {"command": 'python3 /x/scripts/slack_notify.py "電池が 16% だよ"'}},
        {"name": "Bash", "input": {"command": "ls"}},
    ])
    _stream(logs / "20261117_120000_chat_stream.jsonl", [
        {"name": "mcp__m5-ko__save_tts_memo", "input": {"text": "おやすみのメモ"}},
    ])
    ch = tmp_path / "characters" / "ko" / "chat_histories"
    ch.mkdir(parents=True)
    (ch / "chat_history.json").write_text(json.dumps([
        {"role": "user", "text": "やあ", "timestamp": "2026-11-17T03:00:00+00:00"},
        {"role": "ko", "text": "こんにちは、窓をみてた", "timestamp": "2026-11-17T03:00:05+00:00"},
        {"role": "ko", "text": "みんなの方で", "timestamp": "2026-11-17T03:01:00+00:00", "via": "group"},
    ], ensure_ascii=False), encoding="utf-8")
    g = tmp_path / "chat_history"
    g.mkdir()
    (g / "group_chat.json").write_text(json.dumps([
        {"role": "ko", "text": "みんなの方で", "timestamp": "2026-11-17T03:01:00+00:00"},
        {"role": "teya", "text": "別の子", "timestamp": "2026-11-17T03:02:00+00:00"},
    ], ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_collects_each_kind_once(tmp_path):
    base = _house(tmp_path)
    assert said.update(base, "ko") == 5
    assert said.update(base, "ko") == 0
    rows = said.load(said._store(base, "ko")[0])
    assert sorted(r["via"] for r in rows) == ["chat", "group", "memo", "slack", "speak"]
    assert next(r for r in rows if r["via"] == "slack")["text"] == "電池が 16% だよ"
    assert next(r for r in rows if r["via"] == "chat")["ts"].startswith("2026-11-17T12:00:05")   # JST


def test_search_words_and_via(tmp_path):
    base = _house(tmp_path)
    assert [r["via"] for r in said.find(base, "ko", "窓")] == ["speak", "chat"]
    assert [r["text"] for r in said.find(base, "ko", "", vias=["slack"])] == ["電池が 16% だよ"]


def test_new_history_is_added(tmp_path):
    base = _house(tmp_path)
    said.update(base, "ko")
    p = base / "characters" / "ko" / "chat_histories" / "chat_history.json"
    items = json.loads(p.read_text(encoding="utf-8"))
    items.append({"role": "ko", "text": "あとから", "timestamp": "2026-11-17T05:00:00+00:00"})
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    assert said.update(base, "ko") == 1


def test_slack_text_stops_at_shell_ops():
    assert said._slack_text('python3 a/slack_notify.py "やあ" 2>&1 && echo ok') == "やあ"
    assert said._slack_text("echo hi") is None
