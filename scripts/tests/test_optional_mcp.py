"""つないだときだけ使う道具(scripts/optional_mcp.py)のテスト"""

import json
import stat
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import optional_mcp as om  # noqa: E402

T0 = datetime(2026, 11, 14, 22, 0)


def _house(tmp_path, on):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "optional_mcp.json").write_text(json.dumps({"servers": {"mod": {"label": "外付け", "on": on, "devices": [
        {"name": "ENV", "hosts": ["e1", "e2"], "tools": ["get_env", "get_ble"]},
        {"name": "GPS", "hosts": ["g1"], "port": 8080, "tools": ["get_gps"]}]}}}), encoding="utf-8")
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"memory": {"command": "m"}, "mod": {"command": "x", "env": {"KEY": "secret"}}}}), encoding="utf-8")
    return cfg


def test_off_drops_server_without_probing(tmp_path):
    cfg = _house(tmp_path, False)
    asked = []
    path, drop = om.apply(tmp_path, cfg, T0, lambda h, p: asked.append(h) or True)
    assert asked == [] and drop == [] and path != cfg
    assert sorted(json.loads(path.read_text(encoding="utf-8"))["mcpServers"]) == ["memory"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600   # 鍵が入っていることがあるので、持ち主だけ
    assert json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["mod"]   # 元の設定は書き換えない


def test_on_follows_devices_and_caches(tmp_path):
    cfg = _house(tmp_path, True)
    asked = []
    alive = {"e2": True}
    probe = lambda h, p: asked.append((h, p)) or alive.get(h, False)  # noqa: E731
    # ENV だけ見つかる → サーバーは残し、GPS の道具を止める
    assert om.apply(tmp_path, cfg, T0, probe) == (cfg, ["mcp__mod__get_gps"])
    assert asked == [("e1", 80), ("e2", 80), ("g1", 8080)]
    # すぐあとは、探し直さない
    assert om.apply(tmp_path, cfg, datetime(2026, 11, 14, 22, 1), probe) == (cfg, ["mcp__mod__get_gps"]) and len(asked) == 3
    # 時間がたって、どれも見つからない → サーバーごと外す
    alive.clear()
    path, drop = om.apply(tmp_path, cfg, datetime(2026, 11, 14, 22, 5), probe)
    assert path != cfg and drop == [] and len(asked) == 6
    st = om.status(tmp_path, datetime(2026, 11, 14, 22, 5), probe)["mod"]
    assert st["use"] is False and [d["alive"] for d in st["devices"]] == [False, False]
    # ぜんぶ見つかる
    alive.update({"e1": True, "g1": True})
    assert om.apply(tmp_path, cfg, datetime(2026, 11, 14, 22, 9), probe) == (cfg, [])


def test_no_config_or_unknown_server_changes_nothing(tmp_path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"memory": {"command": "m"}}}), encoding="utf-8")
    assert om.apply(tmp_path, cfg, T0) == (cfg, [])   # 家の設定が無い
    _house(tmp_path, False)
    cfg.write_text(json.dumps({"mcpServers": {"memory": {"command": "m"}}}), encoding="utf-8")
    assert om.apply(tmp_path, cfg, T0) == (cfg, [])   # その設定に、外すサーバーが入っていない
    assert om.apply(tmp_path, tmp_path / "none.json", T0) == (tmp_path / "none.json", [])
    om.set_on(tmp_path, "mod", True)
    assert om.load(tmp_path)["mod"]["on"] is True
    with pytest.raises(ValueError):
        om.set_on(tmp_path, "nope", True)
