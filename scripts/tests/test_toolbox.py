"""道具箱(scripts/toolbox.py)のテスト"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import toolbox as tb


def _ev(name, inp=None):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t", "name": name, "input": inp or {}}]}}) + "\n"


def house(tmp_path: Path) -> Path:
    d = tmp_path / ".autonomous-logs" / "puchi"
    d.mkdir(parents=True)
    (d / "20261115_220001_stream.jsonl").write_text(_ev("mcp__m5-mcp__get_sensor_data") + _ev("mcp__memory__remember") + _ev("Bash", {"command": "python3 /x/scripts/write_mailbox.py puchi other hi"}) + '{"type":"result"}\n', encoding="utf-8")
    (d / "20261116_120001_chat_stream.jsonl").write_text(_ev("mcp__m5-puchi__speak") + _ev("mcp__memory-puchi__recall_divergent") + _ev("Read", {"file_path": "x"}) + _ev("mcp__weird-server__thing"), encoding="utf-8")
    (d / "20261001_000001_stream.jsonl").write_text(_ev("mcp__memory__tom"), encoding="utf-8")   # 古い(数えない)
    return tmp_path


def test_tool_key():
    assert tb.tool_key("mcp__m5-mcp__speak") == "m5:speak" == tb.tool_key("mcp__m5-puchiko__speak")
    assert tb.tool_key("mcp__memory-puchiru__recall") == "memory:recall" and tb.tool_key("mcp__desire-system-puchiko__get_desires") == "desire:get_desires"
    assert tb.tool_key("mcp__m5-module__get_env") == "module:get_env" and tb.tool_key("mcp__petit-sns__sns_post") == "sns:sns_post"
    assert tb.tool_key("Bash", {"command": "cd x && python3 /a/b/scripts/mail_tags.py pending puchi"}) == "script:mail_tags"
    assert tb.tool_key("Bash", {"command": "ls"}) == "claude:Bash" and tb.tool_key("WebSearch") == "claude:WebSearch"


def test_usage_counts_and_shelves(tmp_path):
    base = house(tmp_path)
    u = tb.usage(base, "puchi", days=14, now=datetime(2026, 11, 16, 15, 0))
    assert u["m5:get_sensor_data"]["count"] == 1 and u["m5:get_sensor_data"]["alone"] == 1 and u["m5:get_sensor_data"]["last"] == "2026-11-15T22:00"
    assert u["m5:speak"]["chat"] == 1 and u["script:write_mailbox"]["count"] == 1 and u["claude:Read"]["count"] == 1
    assert "memory:tom" not in u   # 期間の外
    shelves = tb.shelves_with({"puchi": u})
    by_id = {s["id"]: s for s in shelves}
    assert by_id["memory"]["tools"][0]["key"] == "memory:remember" and by_id["memory"]["tools"][0]["usage"]["puchi"]["count"] == 1
    assert any(t["key"] == "memory:recall_divergent" and t["usage"]["puchi"]["count"] == 1 for t in by_id["memory"]["tools"])
    assert [t["key"] for t in by_id["other"]["tools"]] == ["weird-server:thing"]   # 知らない鍵は「ほか」
    assert tb.usage(base, "nobody") == {}


def test_hand_once_a_day_notice_once_and_felt(tmp_path):
    base = house(tmp_path)
    (base / "config").mkdir(); (base / "config" / "people.json").write_text(json.dumps({"arisan": {"name": "ありさん"}}), encoding="utf-8")
    t = datetime(2026, 11, 16, 15, 0)
    r = tb.hand(base, "arisan", "puchi", "memory:recall_divergent", "紫を引いてみる?", now=t)
    assert r["to"] == "puchi" and r["told"] is None
    try:
        tb.hand(base, "arisan", "puchi", "memory:tom", now=t)
        raise AssertionError
    except ValueError:
        pass
    tb.hand(base, "arisan", "other", "memory:tom", now=t)   # 別の子には渡せる
    lines = tb.notice(base, "puchi", mark=True)
    assert len(lines) == 1 and lines[0].startswith("（ありさんが道具箱から 1 つ渡してくれた: memory:recall_divergent「記憶を違う方向から引く」。一言「紫を引いてみる?」。使っても使わなくてもいい。")
    assert "--skip" in lines[0]
    assert tb.notice(base, "puchi", mark=True) == []   # もう伝えた
    f = tb.felt(base, "puchi", "違う色が出てきた", now=t)
    assert f["tool"] == "memory:recall_divergent" and f["skip"] is False
    s = tb.felt(base, "puchi", "今日は手が向かなかった", skip=True, now=t)
    assert s["skip"] is True
    lg = tb.log(base)
    assert len(lg["handed"]) == 2 and len(lg["felt"]) == 2 and lg["handed"][0]["told"]
