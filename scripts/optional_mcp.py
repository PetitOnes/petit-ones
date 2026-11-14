#!/usr/bin/env python3
"""つないだときだけ使う道具(MCP サーバー): 「使う」と決めてあって、機体がいま見つかるときだけ、ぷちに渡す。

外付けのセンサーのように、つないでいないことがある機体の道具は、つないでいないあいだ渡しても
タイムアウトするだけになる。そこで、ぷちを呼ぶ直前に MCP の設定から外す(自律行動・ダッシュボードの会話)。

家の設定 PETIT_DATA_DIR/config/optional_mcp.json(git には入れない。⚙️ 設定 → 家 で「使う / 使わない」):

    {"servers": {"m5-module": {"label": "外付けのセンサー", "on": false, "devices": [
        {"name": "ENV PRO", "hosts": ["192.168.1.55"], "port": 80, "tools": ["get_env", "get_ble_rssi"]},
        {"name": "GPS",     "hosts": ["192.168.1.56"], "port": 80, "tools": ["get_gps"]}]}}}

- servers のキーは、MCP の設定(autonomous-mcp.json など)の mcpServers の名前
- on: 使うか。false なら、機体を探しもせずに外す
- devices: そのサーバーが聞きに行く機体。hosts のどれかに port(既定 80)でつながれば「見つかった」
  - どの機体も見つからない → サーバーごと外す
  - 一部だけ見つからない → サーバーは残し、その機体の tools を止める(--disallowedTools に足す)
  - devices が無ければ、on だけで決める
- 探した結果は PETIT_DATA_DIR/state/optional_mcp.json に CACHE_S 秒おぼえる(会話のたびに待たせないため)

Usage:
    optional_mcp.py status [--fresh]          # サーバーごとの、使うか・機体が見つかるか
    optional_mcp.py apply --config <path>     # 1 行目: 使う MCP 設定のパス(外すものが無ければ元のまま)、2 行目: 止める道具(カンマ区切り)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

CACHE_S = 120
PROBE_TIMEOUT_S = 0.7
Probe = Callable[[str, int], bool]


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def config_path(base: Path) -> Path:
    return base / "config" / "optional_mcp.json"


def load(base: Path) -> dict[str, dict]:
    servers = _json(config_path(base), {}).get("servers", {})
    return {k: v for k, v in servers.items() if isinstance(v, dict)} if isinstance(servers, dict) else {}


def set_on(base: Path, server: str, on: bool) -> None:
    d = _json(config_path(base), {})
    servers = d.get("servers") if isinstance(d, dict) else None
    if not isinstance(servers, dict) or not isinstance(servers.get(server), dict):
        raise ValueError("その道具はありません")
    servers[server]["on"] = bool(on)
    p = config_path(base)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def tcp_probe(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=PROBE_TIMEOUT_S):
            return True
    except OSError:
        return False


def _alive(dev: dict, probe: Probe) -> bool:
    try:
        port = int(dev.get("port", 80))
    except (TypeError, ValueError):
        port = 80
    return any(probe(str(h), port) for h in dev.get("hosts") or [] if h)


def status(base: Path, now: datetime | None = None, probe: Probe | None = None, fresh: bool = False) -> dict[str, dict]:
    """サーバーごとに {"label", "on", "devices": [{"name", "alive"}], "use": 渡すか, "drop_tools": [止める道具の名前]}"""
    now = now or datetime.now()
    probe = probe or tcp_probe
    cache_path = base / "state" / "optional_mcp.json"
    cache = _json(cache_path, {})
    cache = cache if isinstance(cache, dict) else {}
    out: dict[str, dict] = {}
    dirty = False
    for name, cfg in load(base).items():
        on = cfg.get("on") is True
        devices = [d for d in cfg.get("devices") or [] if isinstance(d, dict)]
        rows = []
        if on and devices:   # 使わないと決めてあるものは、探さない
            old = cache.get(name) if isinstance(cache.get(name), dict) else {}
            try:
                is_fresh = (now - datetime.fromisoformat(old.get("at", ""))).total_seconds() < CACHE_S
            except (TypeError, ValueError):
                is_fresh = False
            if is_fresh and not fresh and len(old.get("alive") or []) == len(devices):
                alive = [bool(a) for a in old["alive"]]
            else:
                alive = [_alive(d, probe) for d in devices]
                cache[name] = {"at": now.isoformat(timespec="seconds"), "alive": alive}
                dirty = True
            rows = [{"name": str(d.get("name") or f"機体 {i + 1}"), "alive": a} for i, (d, a) in enumerate(zip(devices, alive))]
        else:
            rows = [{"name": str(d.get("name") or f"機体 {i + 1}"), "alive": None} for i, d in enumerate(devices)]
        use = on and (not devices or any(r["alive"] for r in rows))
        drop = [f"mcp__{name}__{t}" for d, r in zip(devices, rows) if use and not r["alive"] for t in d.get("tools") or []]
        out[name] = {"label": str(cfg.get("label") or name), "on": on, "devices": rows, "use": use, "drop_tools": drop}
    if dirty:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return out


def apply(base: Path, mcp_config: Path, now: datetime | None = None, probe: Probe | None = None) -> tuple[Path, list[str]]:
    """MCP の設定から、いま渡さないサーバーを外す。(使う設定のパス, 止める道具) を返す。

    外すものが無ければ元のパスのまま。外すときは PETIT_DATA_DIR/state/mcp_filtered/ に写しを置く
    (設定には鍵が入っていることがあるので、持ち主だけが読める形で)。読めない設定は、元のまま返す
    """
    st = status(base, now, probe)
    d = _json(mcp_config, None)
    servers = d.get("mcpServers") if isinstance(d, dict) else None
    if not st or not isinstance(servers, dict):
        return mcp_config, []
    gone = [n for n, s in st.items() if n in servers and not s["use"]]
    drop = [t for n, s in st.items() if n in servers and s["use"] for t in s["drop_tools"]]
    if not gone:
        return mcp_config, drop
    d = {**d, "mcpServers": {k: v for k, v in servers.items() if k not in gone}}
    out_dir = base / "state" / "mcp_filtered"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{hashlib.sha1(str(mcp_config).encode()).hexdigest()[:12]}.json"
    text = json.dumps(d, ensure_ascii=False, indent=2) + "\n"
    if _json(out, None) != d:
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
    return out, drop


def main() -> int:
    ap = argparse.ArgumentParser(description="つないだときだけ使う道具(MCP サーバー)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("status")
    p.add_argument("--fresh", action="store_true")
    p = sub.add_parser("apply")
    p.add_argument("--config", required=True)
    a = ap.parse_args()
    base = data_dir()
    if a.cmd == "status":
        for name, s in status(base, fresh=a.fresh).items():
            devs = "、".join(f"{d['name']} {'見つかった' if d['alive'] else '探していない' if d['alive'] is None else '見つからない'}" for d in s["devices"])
            print(f"{s['label']}({name}): {'使う' if s['on'] else '使わない'} / {'渡す' if s['use'] else '渡さない'}" + (f" / {devs}" if devs else ""))
        return 0
    path, drop = apply(base, Path(a.config))
    print(path)
    print(",".join(drop))
    return 0


if __name__ == "__main__":
    sys.exit(main())
