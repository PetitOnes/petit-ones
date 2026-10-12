"""create_character.py のテスト。実データに触れず tmp_path に作る(crontab は呼ばない)。

実行: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest scripts/tests/test_create_character.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import create_character as cc


@pytest.fixture
def textbook(tmp_path: Path) -> Path:
    t = tmp_path / "textbook" / "petit" / "templates"
    (t / "data").mkdir(parents=True)
    (t / "config").mkdir()
    (t / "SOUL.md").write_text("# SOUL.md - {名前}の魂\n{色の名前}（{#hex}）、{一緒に暮らす人の呼び名}のそば\n", encoding="utf-8")
    for n in ("SOUL_REFLECTIONS.md", "REFLECTION_INDEX.md", "ROUTINES.md", "ROUTINES_DETAIL.md", "TODO_ACTIVE.md", "TODO_ARCHIVE.md"):
        (t / n).write_text(f"# {n} {{名前}}\n", encoding="utf-8")
    (t / "data" / "relations.json").write_text('{"self": {}, "{一緒に暮らす人のID}": {"feeling": "よく近くにいる存在"}}', encoding="utf-8")
    (t / "config" / "desire_config.json").write_text('{"desires": {"miss_companion": {"name_ja": "{一緒に暮らす人の呼び名}に会いたい"}}}', encoding="utf-8")
    return tmp_path / "textbook"


def _create(tmp_path: Path, textbook: Path, **kw):
    chars = tmp_path / "data" / "characters"
    return cc.create_character(
        "puchitaro", "ぷちたろう", "#f5956e", ["puchitaro.local", "192.168.8.104"],
        color_name=kw.pop("color_name", "あんず"), companion_id="arisan", companion_name="ありさん",
        textbook_dir=textbook, characters_dir=chars, no_cron=True, **kw,
    )


def test_templates_are_copied_and_filled(tmp_path, textbook):
    d = _create(tmp_path, textbook)
    soul = (d / "SOUL.md").read_text(encoding="utf-8")
    assert "ぷちたろうの魂" in soul and "あんず（#f5956e）" in soul and "ありさんのそば" in soul
    assert "{" not in soul
    rel = json.loads((d / "data" / "relations.json").read_text(encoding="utf-8"))
    assert rel["arisan"]["feeling"] == "よく近くにいる存在"
    des = json.loads((d / "config" / "desire_config.json").read_text(encoding="utf-8"))
    assert des["desires"]["miss_companion"]["name_ja"] == "ありさんに会いたい"
    for sub in cc.SUBDIRS:
        assert (d / sub).is_dir()


def test_config_and_mcp(tmp_path, textbook):
    d = _create(tmp_path, textbook)
    cfg = json.loads((d / "config" / "config.json").read_text(encoding="utf-8"))
    assert cfg["m5_host"] == "puchitaro.local" and cfg["m5_hosts"] == ["puchitaro.local", "192.168.8.104"]
    mcp = json.loads((d / "config" / "autonomous-mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert set(mcp) == {"memory", "desire-system", "m5-mcp", "notes", "relations", "textbook"}
    assert mcp["m5-mcp"]["env"]["M5_HOSTS"] == "puchitaro.local,192.168.8.104"
    assert mcp["m5-mcp"]["env"]["M5_CHARACTER_IDS"] == "puchitaro"
    assert mcp["relations"]["env"]["OWNER_ID"] == "arisan"
    assert mcp["textbook"]["env"]["PETIT_TEXTBOOK_DIR"] == str(textbook)
    assert str(tmp_path / "data") in mcp["relations"]["env"]["RELATIONS_PATH"]
    chat = json.loads((d / "config" / "chat-mcp.json").read_text(encoding="utf-8"))
    assert chat["mcpServers"] == mcp
    settings = json.loads((d / "config" / "settings.json").read_text(encoding="utf-8"))
    assert settings["max_turns"] == 20


def test_existing_dir_requires_force_and_keeps_files(tmp_path, textbook):
    d = _create(tmp_path, textbook)
    (d / "SOUL.md").write_text("mine", encoding="utf-8")
    with pytest.raises(SystemExit):
        _create(tmp_path, textbook)
    _create(tmp_path, textbook, force=True)
    assert (d / "SOUL.md").read_text(encoding="utf-8") == "mine"


def test_siblings_and_inherited_env(tmp_path, textbook):
    chars = tmp_path / "data" / "characters"
    sib = chars / "puchiko" / "config"
    sib.mkdir(parents=True)
    (sib / "config.json").write_text("{}", encoding="utf-8")
    (sib / "autonomous-mcp.json").write_text(json.dumps({"mcpServers": {"m5-mcp": {"env": {"VOICE_API_HOST": "gpu-box", "M5_HOSTS": "x"}}}}), encoding="utf-8")
    d = _create(tmp_path, textbook)
    env = json.loads((d / "config" / "autonomous-mcp.json").read_text(encoding="utf-8"))["mcpServers"]["m5-mcp"]["env"]
    assert env["VOICE_API_HOST"] == "gpu-box"
    assert env["M5_HOSTS"] == "puchitaro.local,192.168.8.104"
    assert env["M5_CHARACTER_IDS"] == "puchiko / puchitaro"
    assert env["M5_PERSON_IDS"] == "puchiko / puchitaro / arisan"


def test_cron_offset_picks_free_slot():
    tab = "0,30 * * * * /x/autonomous-action.sh puchiteya\n5,35 * * * * /x/autonomous-action.sh puchiko\n10,40 * * * * /x/autonomous-action.sh puchiru\n"
    assert cc.used_offsets(tab) == {0, 5, 10}
    assert cc.pick_offset(tab) == 15
    lines = cc.cron_lines("puchitaro", 15, project_dir=Path("/p"), data_dir=Path("/d"), uv="uv")
    assert lines[1] == "15,45 * * * * /p/autonomous-action.sh puchitaro"
    assert "src/m5-petit-desire" in lines[0] and "desire_updater.py puchitaro" in lines[0]


def test_validation(tmp_path, textbook):
    with pytest.raises(SystemExit):
        cc.create_character("Bad-Id", "x", "#ffffff", ["h"], color_name=None, companion_id="a", companion_name="a", textbook_dir=textbook, characters_dir=tmp_path, no_cron=True)
    with pytest.raises(SystemExit):
        cc.create_character("ok", "x", "ffffff", ["h"], color_name=None, companion_id="a", companion_name="a", textbook_dir=textbook, characters_dir=tmp_path, no_cron=True)
