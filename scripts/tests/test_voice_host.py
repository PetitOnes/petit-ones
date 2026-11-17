"""声と聞き取りの機械(scripts/voice_host.py)と、MCP 設定への反映(optional_mcp.apply)のテスト"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import optional_mcp as om  # noqa: E402
import voice_host as vh  # noqa: E402


def _cfg(tmp_path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"memory": {"command": "m"},
                                              "m5-mcp": {"command": "x", "env": {"VOICE_API_HOST": "localhost", "KEY": "secret"}}}}), encoding="utf-8")
    return cfg


def test_no_house_setting_keeps_original(tmp_path, monkeypatch):
    monkeypatch.delenv("VOICE_API_HOST", raising=False)
    cfg = _cfg(tmp_path)
    assert vh.get(tmp_path) is None and vh.current(tmp_path) == "localhost"
    assert om.apply(tmp_path, cfg) == (cfg, [])


def test_house_setting_rewrites_copy_only(tmp_path):
    cfg = _cfg(tmp_path)
    vh.set_host(tmp_path, "puchipuchi")
    assert vh.current(tmp_path) == "puchipuchi"
    path, drop = om.apply(tmp_path, cfg)
    assert path != cfg and drop == []
    servers = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]
    assert servers["m5-mcp"]["env"] == {"VOICE_API_HOST": "puchipuchi", "KEY": "secret"} and servers["memory"] == {"command": "m"}
    assert json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["m5-mcp"]["env"]["VOICE_API_HOST"] == "localhost"   # 元は書き換えない


def test_same_host_and_unset(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    vh.set_host(tmp_path, "localhost")
    assert om.apply(tmp_path, cfg) == (cfg, [])   # もう同じなら写しは作らない
    vh.set_host(tmp_path, None)
    monkeypatch.setenv("VOICE_API_HOST", "puchipuchi")
    assert vh.get(tmp_path) is None and vh.current(tmp_path) == "puchipuchi"   # 決めていなければ環境変数


def test_bad_host(tmp_path):
    with pytest.raises(ValueError):
        vh.set_host(tmp_path, "evil.example.com")
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "voice.json").write_text('{"host": "a b; rm"}', encoding="utf-8")
    assert vh.get(tmp_path) is None
