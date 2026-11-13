"""欲求の様子(その子の欲求が、この数日どう動いたか)。

家にいまあるものから組み立てるだけで、新しく何も書かない:

- 欲求の決まり … characters/<id>/config/desire_config.json(名前・満たすまでの時間・満たしたことになる言葉・体や他の欲求からの効き方)
- 強さの記録 … .autonomous-logs/<id>/desire-YYYYMMDD.log(desire_updater が 5 分ごとに書く 1 行)
- 満たした記憶 … 記憶 DB で、その欲求の言葉(keywords)を含む記憶の時刻。欲求は、最後のそれからの時間で上がる
- 道具で満たした回数 … 自律行動の記録にある satisfy_desire の呼び出し
"""

from __future__ import annotations

import ast
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DAYS_MAX = 31
FULL = 0.999   # これ以上を「上限に張りついている」と数える
_LINE = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] \[desire-updater\] 更新完了: dominant=(\w+) desires=(\{.*\})")
_SATISFY = re.compile(r'"name":\s*"mcp__desire-system[\w-]*__satisfy_desire",\s*"input":\s*\{"desire_name":\s*"(\w+)"')


def _samples(log_dir: Path, start: datetime, end: datetime) -> list[tuple[datetime, str, dict]]:
    """強さの記録を、古い順に (時刻, いちばん強かった欲求, {欲求: 強さ})"""
    out = []
    day = start.date()
    while day <= end.date():
        try:
            lines = (log_dir / f"desire-{day.strftime('%Y%m%d')}.log").read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            lines = []
        for line in lines:
            m = _LINE.match(line)
            if not m:
                continue
            try:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                levels = ast.literal_eval(m.group(3))
            except (ValueError, SyntaxError):
                continue
            if start <= ts <= end and isinstance(levels, dict):
                out.append((ts, m.group(2), levels))
        day += timedelta(days=1)
    return out


def _satisfied_times(memory_db: Path, keywords: list[str], start: datetime) -> list[str]:
    """その欲求の言葉を含む記憶の時刻(start からあと、古い順)"""
    if not keywords or not memory_db.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{memory_db}?mode=ro", uri=True)
        cond = " OR ".join("content LIKE ?" for _ in keywords)
        rows = conn.execute(
            f"SELECT timestamp FROM memories WHERE timestamp >= ? AND ({cond}) ORDER BY timestamp",
            [start.isoformat(), *[f"%{k}%" for k in keywords]],
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    return [r[0][:19] for r in rows if r[0]]


def _tool_satisfies(log_dir: Path, start: datetime) -> dict[str, int]:
    """自律行動・会話の記録で、satisfy_desire を呼んだ回数(欲求ごと)"""
    counts: dict[str, int] = {}
    try:
        files = [f for f in log_dir.iterdir() if f.name.endswith("_stream.jsonl")]
    except OSError:
        return counts
    for f in files:
        try:
            if datetime.strptime(f.name[:15], "%Y%m%d_%H%M%S") < start - timedelta(hours=1):
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
        except (ValueError, OSError):
            continue
        if "satisfy_desire" not in text:
            continue
        for name in _SATISFY.findall(text):
            counts[name] = counts.get(name, 0) + 1
    return counts


def build(char_dir: Path, log_dir: Path, memory_db: Path, days: int = 7, now: datetime | None = None) -> dict:
    """その子の欲求の様子。days 日ぶん。

    返すもの: {"from", "to", "times": [...], "desires": [{"id", "name", "color", "description", "hours", "keywords",
    "time_driven", "base_level", "values": [...], "now", "full_pct", "top_pct", "mean", "satisfied": [...], "tool_satisfied"}],
    "sensor_effects": [...], "cross_effects": [...], "priority": [...], "samples"}
    """
    now = now or datetime.now()
    days = max(1, min(days, DAYS_MAX))
    start = now - timedelta(days=days)
    try:
        cfg = json.loads((char_dir / "config" / "desire_config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cfg = {}
    desires_cfg = cfg.get("desires") if isinstance(cfg.get("desires"), dict) else {}
    samples = _samples(log_dir, start, now)
    tool = _tool_satisfies(log_dir, start)
    n = len(samples)
    ids = list(desires_cfg) + sorted({k for _, _, lv in samples for k in lv} - set(desires_cfg))
    desires = []
    for did in ids:
        d = desires_cfg.get(did, {}) if isinstance(desires_cfg.get(did, {}), dict) else {}
        values = [lv.get(did) for _, _, lv in samples]
        seen = [v for v in values if isinstance(v, (int, float))]
        keywords = [k for k in d.get("keywords", []) if isinstance(k, str)]
        desires.append({
            "id": did, "name": d.get("name_ja", did), "color": d.get("color", "#cab8d9"), "description": d.get("description", ""),
            "hours": d.get("satisfaction_hours"), "keywords": keywords,
            "time_driven": d.get("time_driven", True), "base_level": d.get("base_level"),
            "values": values, "now": seen[-1] if seen else None,
            "full_pct": round(100 * sum(v >= FULL for v in seen) / len(seen)) if seen else None,
            "top_pct": round(100 * sum(top == did for _, top, _ in samples) / n) if n else None,
            "mean": round(sum(seen) / len(seen), 2) if seen else None,
            "satisfied": _satisfied_times(memory_db, keywords, start),
            "tool_satisfied": tool.get(did, 0),
        })

    def _desc(items: object) -> list[str]:
        return [str(i.get("description", "")) for i in items if isinstance(i, dict) and i.get("description")] if isinstance(items, list) else []

    return {
        "from": start.isoformat(timespec="seconds"), "to": now.isoformat(timespec="seconds"), "samples": n,
        "times": [ts.isoformat(timespec="minutes") for ts, _, _ in samples],
        "desires": desires,
        "sensor_effects": _desc(cfg.get("sensor_effects")), "cross_effects": _desc(cfg.get("cross_effects")),
        "priority": [p for p in cfg.get("priority", []) if isinstance(p, str)],
    }
