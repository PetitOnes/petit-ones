#!/usr/bin/env python3
"""声(合成 :8766)と聞き取り(文字起こし・話者 :8765)をどの機械でするか。⚙️ 設定 → 家 →「🎙 声と聞き取りの機械」。

家の設定 PETIT_DATA_DIR/config/voice.json(git には入れない):

    {"host": "puchipuchi"}      # GPU 機。"localhost" ならこの PC
    {"sound_host": "puchipuchi"}  # 🔊 音を聞かせる(音の種類 /sound_events)をする機械。無ければ host と同じ

- 無ければ何もしない(MCP 設定の env と、ダッシュボードの環境変数 VOICE_API_HOST のまま)
- ぷちを呼ぶ直前に、MCP 設定の env VOICE_API_HOST を書き換えた写しを使う(optional_mcp.apply の中。元の設定ファイルは書き換えない)
- ダッシュボード自身の声・文字起こしも、これを読む(再起動は要らない)
- 選んだ機械が止まっているときは、部品の側でこの PC(TTS_FALLBACK_URL / ASR_FALLBACK_URL)に落ちる

Usage:
    voice_host.py show
    voice_host.py set --host puchipuchi      # --host "" で決めない(env のまま)に戻す
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

CHOICES = {"localhost": "この PC", "puchipuchi": "puchipuchi(GPU)"}
ENV_KEY = "VOICE_API_HOST"


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def config_path(base: Path) -> Path:
    return base / "config" / "voice.json"


def get(base: Path) -> str | None:
    """家で決めた機械(決めていなければ None)"""
    try:
        d = json.loads(config_path(base).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    h = d.get("host") if isinstance(d, dict) else None
    return h if isinstance(h, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", h) else None


def _read(base: Path) -> dict:
    try:
        d = json.loads(config_path(base).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def sound_host(base: Path) -> str:
    """音の種類を見分ける機械: 家で決めた sound_host → 声と聞き取りの機械"""
    h = _read(base).get("sound_host")
    return h if isinstance(h, str) and h in CHOICES else current(base)


def set_sound_host(base: Path, host: str | None) -> None:
    if host and host not in CHOICES:
        raise ValueError(f"選べるのは {', '.join(CHOICES)}")
    d = _read(base)
    if host:
        d["sound_host"] = host
    else:
        d.pop("sound_host", None)
    _write(base, d)


def _write(base: Path, d: dict) -> None:
    p = config_path(base)
    if not d:
        p.unlink(missing_ok=True)
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)


def current(base: Path) -> str:
    """いま使う機械: 家で決めたもの → 環境変数 VOICE_API_HOST → localhost"""
    return get(base) or os.environ.get(ENV_KEY) or "localhost"


def set_host(base: Path, host: str | None) -> None:
    if host and host not in CHOICES:
        raise ValueError(f"選べるのは {', '.join(CHOICES)}")
    d = _read(base)
    if host:
        d["host"] = host
    else:
        d.pop("host", None)
    _write(base, d)


def override(mcp: dict, host: str | None) -> dict:
    """MCP 設定(mcpServers)のうち、env に VOICE_API_HOST を持つサーバーだけ host に。変えるものが無ければ同じもの"""
    servers = mcp.get("mcpServers") if isinstance(mcp, dict) else None
    if not host or not isinstance(servers, dict):
        return mcp
    out, changed = {}, False
    for name, sv in servers.items():
        env = sv.get("env") if isinstance(sv, dict) else None
        if isinstance(env, dict) and ENV_KEY in env and env[ENV_KEY] != host:
            sv = {**sv, "env": {**env, ENV_KEY: host}}
            changed = True
        out[name] = sv
    return {**mcp, "mcpServers": out} if changed else mcp


def probe(host: str, timeout: float = 1.5) -> dict[str, bool]:
    """その機械の 聞き取り(:8765/health)と 声(:8766/help)が返事をするか"""
    def ok(url: str) -> bool:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.status == 200
        except Exception:
            return False
    asr = ok(f"http://{host}:8765/health") if host != "localhost" else ok("http://localhost:8767/health")
    return {"asr": asr, "tts": ok(f"http://{host}:8766/help")}


def view(base: Path, check: bool = True) -> dict:
    host = current(base)
    return {"host": host, "decided": get(base), "sound_host": sound_host(base), "choices": CHOICES, "env": os.environ.get(ENV_KEY) or None,
            "alive": {h: probe(h) for h in CHOICES} if check else {}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    sp = sub.add_parser("set")
    sp.add_argument("--host", required=True)
    a = ap.parse_args()
    base = data_dir()
    if a.cmd == "set":
        set_host(base, a.host or None)
    print(json.dumps(view(base), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
