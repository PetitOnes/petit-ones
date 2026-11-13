#!/usr/bin/env python3
"""ぷちに渡す文(prompts/ のテンプレート)を組み立てる。

使い方:
    python3 scripts/render_prompt.py autonomous/user --var character_id=puchiko --var-file soul=SOUL.md
    python3 scripts/render_prompt.py chat/system --json vars.json      # 複雑な値(配列・辞書)は JSON で
    echo '{"a": 1}' | python3 scripts/render_prompt.py NAME --json -

探す順: $PETIT_DATA_DIR/prompts/<名前>.md(家ごとの上書き) → <リポ>/prompts/<名前>.md

書き方(最小限の Mustache 風):
    {{var}}                      置き換え(エスケープしない。無い変数は空)
    {{#if var}}…{{/if}}          空・"0"・"false"・空の配列や辞書は偽
    {{#unless var}}…{{/unless}}  その逆
    {{#each list}}…{{/each}}     要素が辞書ならその項目を {{key}} で、スカラーなら {{.}} で
    {{> 名前}}                   別のテンプレートを差し込む(同じ変数で)
ブロックのタグ({{#…}} {{/…}})だけの行は、行ごと消える。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent.parent
_TAG = re.compile(r"\{\{\s*(#if|#unless|#each|/if|/unless|/each|>)?\s*([^{}]*?)\s*\}\}")
_STANDALONE = re.compile(r"^[ \t]*\{\{\s*(?:#if|#unless|#each|/if|/unless|/each)\b[^{}]*\}\}[ \t]*\n", re.M)


def prompt_dirs(data_dir: str | os.PathLike | None = None, project_dir: str | os.PathLike | None = None) -> list[Path]:
    """テンプレートを探すディレクトリ。家の prompts/ が先、リポの prompts/ が後。"""
    data = Path(data_dir or os.environ.get("PETIT_DATA_DIR") or (Path.home() / "petit_claude"))
    proj = Path(project_dir or PROJECT_DIR)
    return [data / "prompts", proj / "prompts"]


def find_template(name: str, data_dir=None, project_dir=None) -> Path:
    for d in prompt_dirs(data_dir, project_dir):
        p = d / f"{name}.md"
        if p.is_file():
            return p
    raise FileNotFoundError(f"テンプレートが無い: {name} (探した: {[str(d) for d in prompt_dirs(data_dir, project_dir)]})")


def find_resource(relpath: str, data_dir=None, project_dir=None) -> Path:
    """テンプレート以外の資料(JSON など)も同じ順で探す。relpath は prompts/ からの相対(拡張子つき)。"""
    for d in prompt_dirs(data_dir, project_dir):
        p = d / relpath
        if p.is_file():
            return p
    raise FileNotFoundError(f"資料が無い: {relpath} (探した: {[str(d) for d in prompt_dirs(data_dir, project_dir)]})")


def truthy(v: Any) -> bool:
    if v is None or v is False:
        return False
    if isinstance(v, str):
        return v.strip() not in ("", "0", "false", "False")
    if isinstance(v, (list, dict, tuple)):
        return len(v) > 0
    return bool(v)


def _lookup(scopes: list[dict], key: str) -> Any:
    if key == ".":
        return scopes[-1].get(".") if scopes else None
    for s in reversed(scopes):
        if key in s:
            return s[key]
    return None


def _parse(text: str) -> list:
    """トークン列を木にする。ノード: str | ("var", key) | ("partial", name) | ("if"/"unless"/"each", key, children)"""
    text = _STANDALONE.sub(_strip_standalone, text)
    pos = 0
    stack: list[tuple[str | None, str | None, list]] = [(None, None, [])]
    for m in _TAG.finditer(text):
        kind, arg = m.group(1), m.group(2)
        if m.start() > pos:
            stack[-1][2].append(text[pos:m.start()])
        pos = m.end()
        if kind is None:
            stack[-1][2].append(("var", arg))
        elif kind == ">":
            stack[-1][2].append(("partial", arg))
        elif kind.startswith("#"):
            stack.append((kind[1:], arg, []))
        else:  # closer
            want = kind[1:]
            k, a, children = stack.pop()
            if k != want:
                raise ValueError(f"ブロックの対応が合わない: {{{{/{want}}}}} に対して開いていたのは {k} {a}")
            stack[-1][2].append((k, a, children))
    if pos < len(text):
        stack[-1][2].append(text[pos:])
    if len(stack) != 1:
        raise ValueError(f"閉じていないブロック: {stack[-1][0]} {stack[-1][1]}")
    return stack[0][2]


def _strip_standalone(m: re.Match) -> str:
    """タグだけの行は、タグだけ残して改行と前後の空白を消す(行が消える)。"""
    return m.group(0).strip(" \t\n")


def _render_nodes(nodes: list, scopes: list[dict], ctx: dict) -> str:
    out: list[str] = []
    for n in nodes:
        if isinstance(n, str):
            out.append(n)
            continue
        kind = n[0]
        if kind == "var":
            v = _lookup(scopes, n[1])
            out.append("" if v is None else (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v)))
        elif kind == "partial":
            out.append(_render_text(_load(n[1], ctx), scopes, ctx))
        elif kind == "if":
            if truthy(_lookup(scopes, n[1])):
                out.append(_render_nodes(n[2], scopes, ctx))
        elif kind == "unless":
            if not truthy(_lookup(scopes, n[1])):
                out.append(_render_nodes(n[2], scopes, ctx))
        elif kind == "each":
            items = _lookup(scopes, n[1]) or []
            if isinstance(items, dict):
                items = [{"key": k, "value": v} for k, v in items.items()]
            for item in items:
                scope = dict(item) if isinstance(item, dict) else {".": item}
                out.append(_render_nodes(n[2], scopes + [scope], ctx))
    return "".join(out)


def _load(name: str, ctx: dict) -> str:
    cache = ctx.setdefault("_cache", {})
    if name not in cache:
        cache[name] = find_template(name, ctx.get("data_dir"), ctx.get("project_dir")).read_text(encoding="utf-8")
    return cache[name]


def _render_text(text: str, scopes: list[dict], ctx: dict) -> str:
    return _render_nodes(_parse(text), scopes, ctx)


def render_text(text: str, variables: dict | None = None, data_dir=None, project_dir=None) -> str:
    """テンプレートの文字列をそのまま組み立てる(テスト・小さな文向け)。"""
    ctx = {"data_dir": data_dir, "project_dir": project_dir}
    return _render_text(text, [dict(variables or {})], ctx)


def render(name: str, variables: dict | None = None, data_dir=None, project_dir=None) -> str:
    """名前でテンプレートを探して組み立てる。"""
    ctx = {"data_dir": data_dir, "project_dir": project_dir}
    return _render_text(_load(name, ctx), [dict(variables or {})], ctx)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="テンプレート名(prompts/ からの相対、拡張子なし)")
    ap.add_argument("--var", action="append", default=[], metavar="K=V", help="文字列の変数")
    ap.add_argument("--var-file", action="append", default=[], metavar="K=PATH", help="ファイルの中身を変数に")
    ap.add_argument("--json", metavar="PATH", help="変数を JSON で(- なら stdin)。--var より先に読む")
    ap.add_argument("--data-dir", default=None, help="家(既定 $PETIT_DATA_DIR か ~/petit_claude)")
    ap.add_argument("--project-dir", default=None, help="リポ(既定はこのスクリプトの親の親)")
    ap.add_argument("--where", action="store_true", help="どのファイルを使うかだけ表示")
    a = ap.parse_args(argv)

    variables: dict[str, Any] = {}
    if a.json:
        raw = sys.stdin.read() if a.json == "-" else Path(a.json).read_text(encoding="utf-8")
        variables.update(json.loads(raw))
    for kv in a.var:
        k, _, v = kv.partition("=")
        variables[k] = v
    for kv in a.var_file:
        k, _, p = kv.partition("=")
        variables[k] = Path(p).read_text(encoding="utf-8")
    if a.where:
        print(find_template(a.name, a.data_dir, a.project_dir))
        return 0
    sys.stdout.write(render(a.name, variables, a.data_dir, a.project_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
