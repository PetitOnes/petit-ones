"""台帳の生成(scripts/gen_prompt_ledger.py)のテスト"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gen_prompt_ledger as gl  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent


def test_every_template_has_a_caller():
    """prompts/ の全部のテンプレートが、どこかのコードか別のテンプレートから使われている(孤児が無い)"""
    templates, _ = gl.collect(REPO, None)
    assert templates, "prompts/ が空"
    orphans = [t.name for t in templates if not t.callers]
    assert not orphans, orphans


def test_parts_extraction():
    t = gl.Template(name="x/y", path=Path("x"), text="{{a}} {{#if b}}{{c}}{{/if}} {{#each L}}{{.}}{{/each}} {{> x/z}}")
    p = t.parts()
    assert p == {"vars": ["a", "c"], "conds": ["b"], "loops": ["L"], "partials": ["x/z"]}


def test_html_and_md_render(tmp_path):
    templates, resources = gl.collect(REPO, tmp_path)   # 家は空 → 上書きなし
    html = gl.render_html(templates, resources, REPO, tmp_path)
    md = gl.render_md(templates, resources, REPO, tmp_path)
    for t in templates:
        assert f"prompts/{t.name}.md" in html and f"prompts/{t.name}.md" in md
    assert "上書きあり: <b>0</b>" in html


def test_house_override_is_shown(tmp_path):
    (tmp_path / "prompts" / "autonomous").mkdir(parents=True)
    (tmp_path / "prompts" / "autonomous" / "routine_mode_normal.md").write_text("家の通常回", encoding="utf-8")
    templates, resources = gl.collect(REPO, tmp_path)
    t = next(t for t in templates if t.name == "autonomous/routine_mode_normal")
    assert t.override and t.override_text == "家の通常回"
    html = gl.render_html(templates, resources, REPO, tmp_path)
    assert "家で上書き中" in html and "家の通常回" in html
