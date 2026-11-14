"""設定のページ(dashboard/ui/settings.html)の道具の一覧が、トップページ(dashboard/main.py の TOOLS)と同じか"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def _main_tools() -> tuple[list[str], list[str]]:
    s = (REPO / "dashboard" / "main.py").read_text(encoding="utf-8")
    block = s[s.index("const TOOLS = {"):]
    block = block[:block.index("};")]
    ids = re.findall(r"^\s*([a-z_]+):\s*\{icon:", block, re.M)
    shown = re.search(r"const TOOLS_DEFAULT_SHOWN = \[([^\]]*)\]", s).group(1)
    return ids, re.findall(r'"([a-z_]+)"', shown)


def _page_tools() -> tuple[list[str], list[str]]:
    s = (REPO / "dashboard" / "ui" / "settings.html").read_text(encoding="utf-8")
    block = s[s.index("const TOOL_LABELS = ["):]
    block = block[:block.index("];")]
    ids = re.findall(r'\["([a-z_]+)", "', block)
    shown = re.search(r"const TOOLS_DEFAULT_SHOWN = \[([^\]]*)\]", s).group(1)
    return ids, re.findall(r'"([a-z_]+)"', shown)


def test_tool_catalog_matches():
    assert _main_tools()[0] == _page_tools()[0]


def test_default_shown_matches():
    assert _main_tools()[1] == _page_tools()[1]
    assert "settings" not in _main_tools()[1]   # 設定は「ほか」の中(2026-11-14 ありさん)


def test_help_anchors_exist():
    """設定ページの「？」の飛び先が、使い方(help.md)の見出しにある"""
    html = (REPO / "dashboard" / "ui" / "settings.html").read_text(encoding="utf-8")
    md = (REPO / "dashboard" / "ui" / "help.md").read_text(encoding="utf-8")
    ids = set(re.findall(r"\{#([a-z0-9-]+)\}", md))
    wanted = set(re.findall(r'data-help="([a-z0-9-]+)"', html))
    assert wanted and wanted <= ids, wanted - ids
    assert len(ids) == len(re.findall(r"\{#([a-z0-9-]+)\}", md))   # 同じ id を 2 回使わない
