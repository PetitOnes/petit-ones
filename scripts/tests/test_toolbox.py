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
    assert tb.tool_key("mcp__m5-module__get_env") == "module:get_env" == tb.tool_key("mcp__m5-module-mcp__get_env") and tb.tool_key("mcp__m5_mcp__speak") == "m5:speak" and tb.tool_key("mcp__petit-sns__sns_post") == "sns:sns_post"
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
    assert [t["key"] for t in by_id["other"]["tools"]] == ["weird-server:thing"]   # 知らない鍵は「ほか」(掃除なし)
    pruned = {s["id"]: s for s in tb.shelves_with({"puchi": {**u, "claude:desires.json": u["claude:Read"], "script:nope": u["claude:Read"], "m5:upload_face": u["claude:Read"]}}, project_dir=tmp_path)}
    assert [t["key"] for t in pruned.get("other", {"tools": []})["tools"]] == ["m5:upload_face"]   # 言い間違い・無い台本・知らない部品は出さない
    assert tb.usage(base, "nobody") == {}
    # まとめた行(音量): どちらかを使えば使ったことに。許されている場の印
    u2 = {"m5:set_volume": {"count": 2, "alone": 2, "chat": 0, "last": "2026-11-16T12:00"}}
    sh = {s["id"]: s for s in tb.shelves_with({"puchi": u2}, {"alone": {"m5:get_volume"}, "chat": set()})}
    vol = next(t for t in sh["body"]["tools"] if t["key"] == "m5:volume")
    assert vol["usage"]["puchi"]["count"] == 2 and vol["allowed"] == {"alone": True, "chat": False} and vol["keys"] == ["m5:get_volume", "m5:set_volume"]
    assert "module:get_ble_rssi" not in tb.labels() and tb.shelf_of("m5:print_text") == "printer"
    assert not tb._is_real("module:get_ble_rssi", tmp_path) and not tb._is_real("m5:set_voice", tmp_path)   # 出さないと決めた道具


def test_allowed_alone_parses_action_script(tmp_path):
    (tmp_path / "autonomous-action.sh").write_text(
        'x\nALLOWED_TOOLS=$(cat <<TOOLS\nRead($ALLOWED_DIR/**),\nWebSearch,\nBash(uv run scripts/reader.py:*),\n'
        'Bash(python3 $ALLOWED_DIR/scripts/write_mailbox.py *),\nmcp__m5-mcp__speak,\nmcp__memory__recall_divergent\nTOOLS\n)\n', encoding="utf-8")
    got = tb.allowed_alone(tmp_path)
    assert got == {"claude:Read", "claude:WebSearch", "script:reader", "script:write_mailbox", "m5:speak", "memory:recall_divergent", "claude:ToolSearch"}
    assert tb.allowed_alone(tmp_path / "nope") == set()
    assert tb.allowed_from_names(["mcp__m5-mcp__take_snapshot", "Read"]) == {"m5:take_snapshot", "claude:Read", "claude:ToolSearch"}
    assert "script:write_mailbox" in tb.allowed_from_names(["Bash"]) and "claude:Bash" in tb.allowed_from_names(["Bash"])   # Bash が丸ごとなら台本もぜんぶ
    cfg = tmp_path / "chat-mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"m5-puchi": {}, "memory-puchi": {}, "petit-sns": {}}}), encoding="utf-8")
    chat = tb.allowed_chat([cfg], {"m5:odd_tool", "weird:thing"})
    assert {"m5:speak", "memory:recall_divergent", "sns:sns_post", "script:write_mailbox", "claude:Read", "m5:odd_tool"} <= chat
    assert "notes:write_note" not in chat and "textbook:textbook_read" not in chat and "weird:thing" not in chat
    assert tb.families_in([tmp_path / "nope.json"]) == set()


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


def test_gates_registered_disallowed_effective(tmp_path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"m5-mcp": {"env": {"M5_ALLOWED_TOOLS": "speak,blink,take_snapshot"}}, "memory": {}, "notes": {}}}), encoding="utf-8")
    reg = tb.registered([cfg])
    assert {"m5:speak", "m5:blink", "memory:recall_divergent", "notes:write_note"} <= reg and "m5:print_text" not in reg   # 体は M5_ALLOWED_TOOLS で絞る
    tb.set_gate(tmp_path, "alone", "m5:blink", False)
    tb.set_gate(tmp_path, "chat", "m5:blink", False)
    tb.set_gate(tmp_path, "alone", "memory:tom", True)       # 許しの一覧に無いものを足す
    tb.set_gate(tmp_path, "chat", "script:mail_tags", False)
    g = tb.gates(tmp_path)
    assert g["alone"] == {"on": ["memory:tom"], "off": ["m5:blink"]} and g["chat"]["off"] == ["m5:blink", "script:mail_tags"]
    assert tb.disallowed(tmp_path, "alone", cfg, Path("/p")) == ["mcp__m5-mcp__blink"]
    assert tb.disallowed(tmp_path, "chat", cfg, Path("/p")) == ["mcp__m5-mcp__blink", "Bash(python3 /p/scripts/mail_tags.py *)"]
    assert tb.extra_allowed(tmp_path, cfg, Path("/p")) == ["mcp__memory__tom"]
    tb.set_gate(tmp_path, "alone", "m5:blink", True, base_allowed={"m5:blink"})         # 開け直すと off から消える(一覧にあるので on には入れない)
    assert tb.gates(tmp_path)["alone"] == {"on": ["memory:tom"], "off": []}
    base_alone = {"m5:speak"}
    assert tb.effective("m5:speak", base_alone, reg, tb.gates(tmp_path)) == {"alone": {"on": True, "can": True}, "chat": {"on": True, "can": True}}
    assert tb.effective("memory:tom", base_alone, reg, tb.gates(tmp_path))["alone"]["on"] is True          # on で足した
    assert tb.effective("m5:print_text", base_alone, reg, tb.gates(tmp_path)) == {"alone": {"on": False, "can": False}, "chat": {"on": False, "can": False}}   # 部品が持っていない
    assert tb.effective("claude:Read", base_alone, reg, tb.gates(tmp_path))["chat"] == {"on": True, "can": False}
    try:
        tb.set_gate(tmp_path, "nope", "x", True)
        raise AssertionError
    except ValueError:
        pass


def test_describe_with_fake_server(tmp_path):
    fake = tmp_path / "fake_mcp.py"
    fake.write_text(
        "import json,sys\n"
        "for line in sys.stdin:\n"
        "    m=json.loads(line)\n"
        "    if m.get('id')==1: print(json.dumps({'jsonrpc':'2.0','id':1,'result':{'protocolVersion':'2024-11-05','capabilities':{},'serverInfo':{'name':'fake','version':'0'}}}),flush=True)\n"
        "    elif m.get('id')==2: print(json.dumps({'jsonrpc':'2.0','id':2,'result':{'tools':[{'name':'remember','description':'覚える。\\n長い説明。','inputSchema':{'properties':{'content':{'description':'中身'}}}}]}}),flush=True)\n",
        encoding="utf-8")
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"memory": {"command": sys.executable, "args": [str(fake)]}, "dead": {"command": sys.executable, "args": ["-c", "pass"]}, "missing": {"command": "no-such-command-xyz"}}}), encoding="utf-8")
    (tmp_path / "scripts").mkdir(); (tmp_path / "scripts" / "sky.py").write_text('"""空のこと。\n\n月と節気。"""\n', encoding="utf-8")
    r = tb.describe(tmp_path, cfg, tmp_path, timeout=5)
    assert r["done"] == ["memory"] and r["failed"] == ["dead", "missing"]   # 立ち上がらない部品も「つながらなかった」
    assert r["tools"]["memory:remember"]["description"].startswith("覚える。") and r["tools"]["memory:remember"]["params"] == [{"name": "content", "desc": "中身"}]
    assert r["tools"]["script:sky"]["description"].startswith("空のこと。")
    assert r["tools"]["claude:Glob"]["server"] == "Claude Code"
    assert tb.descriptions(tmp_path)["tools"]["memory:remember"]["server"] == "memory"
