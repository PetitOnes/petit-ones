"""prompts/ のテンプレート描画(scripts/render_prompt.py)のテスト"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import render_prompt as rp  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent


def test_var_and_missing():
    assert rp.render_text("a={{a}} b={{b}}", {"a": "1"}) == "a=1 b="


def test_if_unless_truthiness():
    t = "{{#if x}}Y{{/if}}{{#unless x}}N{{/unless}}"
    assert rp.render_text(t, {"x": "1"}) == "Y"
    for falsy in ("", "0", "false", None, [], {}):
        assert rp.render_text(t, {"x": falsy}) == "N", repr(falsy)


def test_standalone_block_lines_disappear():
    t = "前\n{{#if x}}\n中\n{{/if}}\n後\n"
    assert rp.render_text(t, {"x": "1"}) == "前\n中\n後\n"
    assert rp.render_text(t, {"x": ""}) == "前\n後\n"


def test_each_dict_items_and_scalars():
    t = "{{#each chars}}- {{name}}({{id}}) {{outer}}\n{{/each}}"
    out = rp.render_text(t, {"chars": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}], "outer": "o"})
    assert out == "- A(a) o\n- B(b) o\n"
    assert rp.render_text("{{#each xs}}[{{.}}]{{/each}}", {"xs": ["1", "2"]}) == "[1][2]"


def test_partial_and_house_override(tmp_path):
    proj = tmp_path / "repo"
    (proj / "prompts" / "x").mkdir(parents=True)
    (proj / "prompts" / "x" / "main.md").write_text("A {{> x/part}} C", encoding="utf-8")
    (proj / "prompts" / "x" / "part.md").write_text("B{{n}}", encoding="utf-8")
    house = tmp_path / "house"
    assert rp.render("x/main", {"n": "1"}, data_dir=house, project_dir=proj) == "A B1 C"
    # 家の prompts/ に同じ名前があればそちらが勝つ
    (house / "prompts" / "x").mkdir(parents=True)
    (house / "prompts" / "x" / "part.md").write_text("家{{n}}", encoding="utf-8")
    assert rp.render("x/main", {"n": "2"}, data_dir=house, project_dir=proj) == "A 家2 C"


def test_unbalanced_block_is_an_error():
    with pytest.raises(ValueError):
        rp.render_text("{{#if a}}x{{/each}}", {"a": "1"})


def test_autonomous_user_template_shape(tmp_path):
    out = rp.render("autonomous/user", {
        "current_date": "2026-11-13 10:00:00", "character_dir": "/h/c/x", "todo_path": "/h/c/x/TODO_ACTIVE.md",
        "diary_summary_line": "@/h/c/x/diary_summary.md", "routine_mode": "通常回。", "time_rule": "昼",
        "project_dir": "/repo", "character_id": "x", "mailbox_notice": "## メールボックス\n送り方",
        "permission_rules": "- カメラは使わない\n",
    }, data_dir=tmp_path, project_dir=REPO)
    order = ["自律行動タイム(Heartbeat)", "@/h/c/x/SOUL.md", "@/h/c/x/TODO_ACTIVE.md", "通常回。", "## 補足ルール", "- 昼",
             "## メールボックス", "## 現在の制限", "- カメラは使わない"]
    idx = [out.index(s) for s in order]
    assert idx == sorted(idx), out
    assert "## 注意: 自分のファイルが重い" not in out and "## 身体の記録" not in out


def test_chat_system_single_and_multi(tmp_path):
    base = {"owner_name": "O", "now": "N", "data_dir": "/d", "scripts_dir": "/s", "mailbox_dir": "/d/mailbox",
            "mail_targets": "a, b, O", "first_id": "a", "name_prefix_examples": "**A**:", "char_count": "1",
            "chars": [{"id": "a", "name": "A", "soul": "SOUL-A", "desires": "欲"}]}
    single = rp.render("chat/system", {**base, "multi": False}, data_dir=tmp_path, project_dir=REPO)
    assert single.startswith("あなたはA（ID: a）です。以下があなたの魂の定義です。\n\nSOUL-A\n")
    assert "複数人チャットのルール" not in single
    multi = rp.render("chat/system", {**base, "multi": True, "char_count": "2",
                      "chars": base["chars"] + [{"id": "b", "name": "B", "soul": "SOUL-B", "desires": "欲"}]},
                      data_dir=tmp_path, project_dir=REPO)
    assert multi.startswith("あなたたちは2人のキャラクターです。")
    assert "## A（ID: a）の魂" in multi and "## B（ID: b）の魂" in multi and "複数人チャットのルール" in multi
