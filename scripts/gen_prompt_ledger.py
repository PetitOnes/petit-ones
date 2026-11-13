#!/usr/bin/env python3
"""prompts/ から「ぷちに渡す文の台帳」を作る(手で写さない)。

使い方:
    python3 scripts/gen_prompt_ledger.py                      # HTML を標準出力に
    python3 scripts/gen_prompt_ledger.py --out /tmp/ledger.html
    python3 scripts/gen_prompt_ledger.py --format md --out docs/prompt-ledger.md

載せるもの(全部 prompts/ とコードから拾う):
- 入口(autonomous / chat / dashboard)ごとのテンプレート一覧。本文そのもの、使っている変数・条件・部品、大きさ
- どのコードから呼ばれているか(autonomous-action.sh・scripts/*.py・dashboard/*.py を grep した file:line)
- 家(PETIT_DATA_DIR/prompts/)に同名の上書きがあるか。あればそちらの本文も並べる
- prompts/dashboard/*.json のような資料
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_DIR = Path(__file__).resolve().parent.parent
TAG = re.compile(r"\{\{\s*(#if|#unless|#each|/if|/unless|/each|>)?\s*([^{}]*?)\s*\}\}")

GROUPS = {
    "autonomous": ("01 自律行動", "autonomous-action.sh が cron 30 分ごとに組み立てる user prompt。system prompt は Claude Code の既定のまま(指定しない)"),
    "chat": ("03 ターミナルチャット", "scripts/build_chat_prompt.py が組み立て、start_chat_session.sh が --system-prompt-file で渡す(Claude Code の既定の system prompt を置き換える)"),
    "dashboard": ("02 ダッシュボード", "dashboard/main.py の _prompt() が組み立てる。会話の system prompt は --append-system-prompt(既定の後ろに足す)、それ以外は user message"),
}
CODE_FILES = ["autonomous-action.sh", "scripts/*.py", "dashboard/*.py"]


@dataclass
class Template:
    name: str            # 例 autonomous/user
    path: Path
    text: str
    override: Path | None = None
    override_text: str = ""
    callers: list[str] = field(default_factory=list)

    @property
    def group(self) -> str:
        return self.name.split("/", 1)[0]

    def parts(self) -> dict[str, list[str]]:
        vars_, conds, loops, partials = [], [], [], []
        for m in TAG.finditer(self.text):
            kind, arg = m.group(1), m.group(2)
            if kind is None:
                if arg != "." and arg not in vars_:
                    vars_.append(arg)
            elif kind in ("#if", "#unless"):
                if arg not in conds:
                    conds.append(arg)
            elif kind == "#each":
                if arg not in loops:
                    loops.append(arg)
            elif kind == ">":
                if arg not in partials:
                    partials.append(arg)
        return {"vars": vars_, "conds": conds, "loops": loops, "partials": partials}


def collect(project_dir: Path, data_dir: Path | None) -> tuple[list[Template], list[Path]]:
    base = project_dir / "prompts"
    templates: list[Template] = []
    resources: list[Path] = []
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.name == "README.md":
            continue
        rel = p.relative_to(base)
        if p.suffix == ".md":
            name = str(rel.with_suffix("")).replace(os.sep, "/")
            t = Template(name=name, path=p, text=p.read_text(encoding="utf-8"))
            if data_dir:
                o = data_dir / "prompts" / rel
                if o.is_file():
                    t.override, t.override_text = o, o.read_text(encoding="utf-8")
            templates.append(t)
        else:
            resources.append(p)
    find_callers(project_dir, templates)
    return templates, resources


def find_callers(project_dir: Path, templates: list[Template]) -> None:
    files: list[Path] = []
    for pat in CODE_FILES:
        files += sorted(project_dir.glob(pat))
    lines_by_file = {f: f.read_text(encoding="utf-8", errors="replace").splitlines() for f in files if f.is_file()}
    for t in templates:
        short = t.name.split("/", 1)[1]
        needles = [t.name]
        if t.group == "dashboard":
            needles.append(f'_prompt("{short}"')
        if t.group == "autonomous":
            needles.append(f"render {t.name}")
        for f, lines in lines_by_file.items():
            for i, line in enumerate(lines, 1):
                if line.lstrip().startswith("#"):
                    continue
                hit = any(n in line for n in needles)
                # _prompt(\n    "name", … のように名前が次の行にあるとき
                if not hit and t.group == "dashboard" and line.strip().startswith(f'"{short}"') and i >= 2 and "_prompt(" in lines[i - 2]:
                    hit = True
                if hit:
                    t.callers.append(f"{f.relative_to(project_dir)}:{i}")
        # 部品として差し込まれている先
        for other in templates:
            if other is not t and f"{{{{> {t.name}}}}}" in other.text.replace("{{>", "{{> ").replace("  ", " "):
                t.callers.append(f"prompts/{other.name}.md(部品として)")


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def render_html(templates: list[Template], resources: list[Path], project_dir: Path, data_dir: Path | None) -> str:
    now = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M")
    groups: dict[str, list[Template]] = {}
    for t in templates:
        groups.setdefault(t.group, []).append(t)
    out: list[str] = []
    out.append(f"""<title>ぷちへのプロンプト台帳(生成)</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
:root{{--bg:#f7f6f2;--panel:#fff;--fg:#23252b;--muted:#6b6e78;--line:#e3e1d9;--accent:#2f5d8a;--accent-soft:#e6eef7;--ok:#2e7d4f;--ok-soft:#e2f2e8;--warn:#b4541a;--warn-soft:#fbeadd;
 --font-body:"Noto Sans JP",system-ui,-apple-system,"Hiragino Sans",sans-serif;--font-mono:ui-monospace,SFMono-Regular,Menlo,monospace}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#16181d;--panel:#1f2229;--fg:#e8e8e4;--muted:#9a9ea8;--line:#30343c;--accent:#7fb0e3;--accent-soft:#223243;--ok:#7fcf9c;--ok-soft:#1f3a2b;--warn:#f0a35e;--warn-soft:#3b2a1c;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#16181d;--panel:#1f2229;--fg:#e8e8e4;--muted:#9a9ea8;--line:#30343c;--accent:#7fb0e3;--accent-soft:#223243;--ok:#7fcf9c;--ok-soft:#1f3a2b;--warn:#f0a35e;--warn-soft:#3b2a1c;color-scheme:dark}}
body{{background:var(--bg);color:var(--fg);font-family:var(--font-body);line-height:1.7;font-size:15px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:0 48px}}
.wrap{{max-width:1040px;margin:0 auto}} h1{{font-size:1.7rem;margin:32px 0 6px}} h2{{font-size:1.2rem;margin:40px 0 4px;padding-top:10px;border-top:2px solid var(--fg)}} h3{{font-size:1rem;margin:0}}
.lead{{color:var(--muted);max-width:66ch}} .mono{{font-family:var(--font-mono);font-size:.86em}} a{{color:var(--accent)}}
.toc{{display:flex;flex-wrap:wrap;gap:8px 16px;font-size:.9rem;margin-top:10px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-top:12px;min-width:0}}
.meta{{display:flex;flex-wrap:wrap;gap:6px 14px;color:var(--muted);font-size:.82rem;margin:6px 0 8px}}
.tag{{display:inline-block;font-size:.72rem;padding:1px 8px;border-radius:999px;border:1px solid var(--line);color:var(--muted);white-space:nowrap}}
.tag.ok{{background:var(--ok-soft);color:var(--ok);border-color:transparent}} .tag.warn{{background:var(--warn-soft);color:var(--warn);border-color:transparent}}
pre{{font-family:var(--font-mono);font-size:.8rem;line-height:1.55;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:10px 12px;overflow-x:auto;white-space:pre-wrap;overflow-wrap:anywhere;margin:0}}
.kv{{font-size:.85rem;color:var(--muted)}} .kv b{{color:var(--fg);font-weight:500}}
details summary{{cursor:pointer;color:var(--accent);font-size:.85rem}}
table{{border-collapse:collapse;width:100%;font-size:.88rem}} th,td{{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}} th{{color:var(--muted);font-weight:500}}
.tablewrap{{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px;margin-top:12px}}
</style>
<div class="wrap">
<h1>ぷちへのプロンプト台帳(生成)</h1>
<p class="lead">このページは <span class="mono">scripts/gen_prompt_ledger.py</span> が <span class="mono">prompts/</span> とコードから作ったもの({now} 生成)。手で写した文はない。
テンプレートの書き方と上書きの決まりは <span class="mono">prompts/README.md</span>。Claude Code 側の既定の system prompt と、11/13 時点の調査(落ちていた添付・入っていた開発用の指示など)は
<a href="https://claude.ai/artifact/DR1qQCmxAKQtZMoxurNqG9">洗い出しのページ</a>のほう。</p>
<p class="kv">家: <b class="mono">{_esc(str(data_dir) if data_dir else '(指定なし)')}</b> / 上書きあり: <b>{sum(1 for t in templates if t.override)}</b> 件 / テンプレート: <b>{len(templates)}</b> 枚 / 資料: <b>{len(resources)}</b></p>
""")
    out.append('<div class="toc">' + " ".join(f'<a href="#g-{g}">{_esc(GROUPS.get(g, (g, ""))[0])}</a>' for g in sorted(groups, key=lambda g: GROUPS.get(g, (g,))[0])) + ' <a href="#summary">一覧表</a></div>')
    # 一覧表
    out.append('<h2 id="summary">一覧表</h2><div class="tablewrap"><table><thead><tr><th>テンプレート</th><th>入口</th><th>呼ぶ所</th><th>変数</th><th>大きさ</th><th>家の上書き</th></tr></thead><tbody>')
    for g in sorted(groups, key=lambda g: GROUPS.get(g, (g,))[0]):
        for t in groups[g]:
            p = t.parts()
            out.append(f'<tr><td><a href="#t-{_esc(t.name).replace("/", "-")}" class="mono">{_esc(t.name)}</a></td><td>{_esc(GROUPS.get(g, (g, ""))[0])}</td>'
                       f'<td class="mono">{"<br>".join(_esc(c) for c in t.callers) or "<span class=tag warn>呼ぶ所が見つからない</span>"}</td>'
                       f'<td class="mono">{_esc(", ".join(p["vars"]))}</td><td>{len(t.text):,} 字</td><td>{"<span class=tag ok>あり</span>" if t.override else "—"}</td></tr>')
    out.append("</tbody></table></div>")
    for g in sorted(groups, key=lambda g: GROUPS.get(g, (g,))[0]):
        title, desc = GROUPS.get(g, (g, ""))
        out.append(f'<h2 id="g-{g}">{_esc(title)}</h2><p class="lead">{_esc(desc)}</p>')
        for t in groups[g]:
            p = t.parts()
            out.append(f'<div class="card" id="t-{_esc(t.name).replace("/", "-")}"><h3><span class="mono">prompts/{_esc(t.name)}.md</span>'
                       + (' <span class="tag ok">家で上書き中</span>' if t.override else '') + '</h3>')
            meta = []
            if p["vars"]:
                meta.append("変数: " + ", ".join(f'<span class="mono">{_esc(v)}</span>' for v in p["vars"]))
            if p["conds"]:
                meta.append("条件: " + ", ".join(f'<span class="mono">{_esc(v)}</span>' for v in p["conds"]))
            if p["loops"]:
                meta.append("繰り返し: " + ", ".join(f'<span class="mono">{_esc(v)}</span>' for v in p["loops"]))
            if p["partials"]:
                meta.append("部品: " + ", ".join(f'<span class="mono">{_esc(v)}</span>' for v in p["partials"]))
            meta.append("呼ぶ所: " + (", ".join(f'<span class="mono">{_esc(c)}</span>' for c in t.callers) or '<span class="tag warn">見つからない</span>'))
            out.append('<div class="meta">' + " · ".join(meta) + "</div>")
            out.append(f"<pre>{_esc(t.text)}</pre>")
            if t.override:
                out.append(f'<details open><summary>家の上書き: <span class="mono">{_esc(str(t.override))}</span></summary><pre>{_esc(t.override_text)}</pre></details>')
            out.append("</div>")
    if resources:
        out.append('<h2 id="resources">資料(テンプレート以外)</h2>')
        for r in resources:
            rel = r.relative_to(project_dir / "prompts")
            out.append(f'<div class="card"><h3><span class="mono">prompts/{_esc(str(rel))}</span></h3><pre>{_esc(r.read_text(encoding="utf-8", errors="replace"))}</pre></div>')
    out.append("</div>")
    return "\n".join(out)


def render_md(templates: list[Template], resources: list[Path], project_dir: Path, data_dir: Path | None) -> str:
    now = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M")
    out = [f"# ぷちへのプロンプト台帳(生成)\n\n`scripts/gen_prompt_ledger.py` が `prompts/` とコードから作ったもの({now} 生成)。\n"]
    groups: dict[str, list[Template]] = {}
    for t in templates:
        groups.setdefault(t.group, []).append(t)
    for g in sorted(groups, key=lambda g: GROUPS.get(g, (g,))[0]):
        title, desc = GROUPS.get(g, (g, ""))
        out.append(f"\n## {title}\n\n{desc}\n")
        for t in groups[g]:
            p = t.parts()
            out.append(f"\n### `prompts/{t.name}.md`" + ("(家で上書き中)" if t.override else ""))
            out.append(f"- 変数: {', '.join(p['vars']) or '—'} / 条件: {', '.join(p['conds']) or '—'} / 繰り返し: {', '.join(p['loops']) or '—'} / 部品: {', '.join(p['partials']) or '—'}")
            out.append(f"- 呼ぶ所: {', '.join(t.callers) or '見つからない'}\n")
            out.append("```\n" + t.text.rstrip("\n") + "\n```")
            if t.override:
                out.append(f"\n家の上書き(`{t.override}`):\n\n```\n{t.override_text.rstrip()}\n```")
    if resources:
        out.append("\n## 資料\n")
        for r in resources:
            out.append(f"\n### `prompts/{r.relative_to(project_dir / 'prompts')}`\n\n```\n{r.read_text(encoding='utf-8', errors='replace').rstrip()}\n```")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="書き出し先(省略で標準出力)")
    ap.add_argument("--format", choices=["html", "md"], default="html")
    ap.add_argument("--data-dir", default=os.environ.get("PETIT_DATA_DIR") or str(Path.home() / "petit_claude"), help="家(上書きを見る)。'' で見ない")
    ap.add_argument("--project-dir", default=str(PROJECT_DIR))
    a = ap.parse_args(argv)
    project_dir = Path(a.project_dir)
    data_dir = Path(a.data_dir) if a.data_dir else None
    templates, resources = collect(project_dir, data_dir)
    text = render_html(templates, resources, project_dir, data_dir) if a.format == "html" else render_md(templates, resources, project_dir, data_dir)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"書いた: {a.out} ({len(templates)} 枚, 上書き {sum(1 for t in templates if t.override)} 件)", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
