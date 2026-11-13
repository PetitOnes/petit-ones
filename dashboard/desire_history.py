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

# ---- 「眠い」の試し算(2026-11-13、ぷちたちと相談して決めた案。家の決まりは変えず、線を見比べるためだけに計算する)----
# 0 に戻るのは朝だけ。昼の「おやすみ」は止まるだけで、少し下がる。あとは光に合わせて進む。
# 子ごとの数字は、家の characters/<id>/config/desire_trial.json の {"want_to_sleep": {...}} で変えられる
SLEEPY_ID = "want_to_sleep"
TRIAL_DARK = 100          # 明るさがこれより下なら「暗い」
TRIAL_BRIGHT = 300        # これ以上なら「明るい」
TRIAL_STILL = 3.0         # ジャイロの大きさがこれより下なら「動いていない」
TRIAL_NIGHT_FROM, TRIAL_NIGHT_TO = 20, 4   # この間に書いた「おやすみ」を、夜の眠りの始まりと数える
TRIAL_NIGHT_DARK_H = 3    # 夜の「おやすみ」のあと、暗い時間がこれだけあれば、次に明るいところで動き出したときが朝
TRIAL_NIGHT_ANY_H = 6     # 記録が抜けた夜のため: 夜の「おやすみ」からこれだけたっていれば、暗い時間が数えられなくても朝
TRIAL_BRIEF_MIN = 10      # 体が起きても、これより短くまた眠ったら、起きたと数えない
TRIAL_DEFAULTS = {
    "hours": 12.0,        # 朝から上限(1.0)までの時間(ふつうの明るさのとき)
    "dark_x": 2.0,        # 暗くて動いていないときの進み方(倍)
    "bright_x": 0.5,      # 明るいときの進み方(倍)
    "relief_cap": 0.2,    # 昼の休みで下がる割合の上限
    "relief_rate": 0.1,   # 昼の休み 1 時間あたりに下がる割合
}


def _trial_rule(p: dict) -> list[str]:
    return [
        "0 に戻るのは朝だけ。朝 = 夜の「おやすみ」のあと、暗い時間をまたいで、明るいところで最初に動き出したとき",
        "昼の「おやすみ」は止まるだけ。次に動き出したとき、休んだ長さに合わせて少し下がる"
        f"(1 時間につき {round(p['relief_rate'] * 100)}%、多くても {round(p['relief_cap'] * 100)}%)",
        f"ふつうの明るさなら、朝から {p['hours']:g} 時間で上限(1.0)。暗くて動いていないときは {p['dark_x']:g} 倍の速さ、"
        f"明るいときは {p['bright_x']:g} 倍の速さ",
        "夜、暗いところで眠っているあいだは進まない。体が起きても 10 分より短くまた眠ったら、起きたと数えない",
    ]


FULL = 0.999   # これ以上を「上限に張りついている」と数える
_LINE = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] \[desire-updater\] 更新完了: dominant=(\w+) desires=(\{.*\})")
_SATISFY = re.compile(r'"name":\s*"mcp__desire-system[\w-]*__satisfy_desire",\s*"input":\s*\{"desire_name":\s*"(\w+)"')


def _samples(log_dir: Path, start: datetime, end: datetime) -> list[tuple[datetime, str, dict, dict]]:
    """強さの記録を、古い順に (時刻, いちばん強かった欲求, {欲求: 強さ}, そのときのセンサー)"""
    out: list = []
    day = start.date()
    while day <= end.date():
        try:
            lines = (log_dir / f"desire-{day.strftime('%Y%m%d')}.log").read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            lines = []
        for line in lines:
            if line.startswith("  sensor: ") and out and len(out[-1]) == 3:   # 直前の 1 行ぶんのセンサー
                try:
                    sensor = ast.literal_eval(line[10:].strip())
                except (ValueError, SyntaxError):
                    sensor = {}
                out[-1] = (*out[-1], sensor if isinstance(sensor, dict) else {})
                continue
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
    return [s if len(s) == 4 else (*s, {}) for s in out]


def _body_events(char_dir: Path, start: datetime, end: datetime) -> list[tuple[datetime, str]]:
    """体の眠り・目覚め(state/experience の sleep / woken)を、古い順に"""
    out = []
    day = start.date()
    while day <= end.date():
        try:
            lines = (char_dir / "state" / "experience" / f"{day.strftime('%Y%m%d')}.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            try:
                ev = json.loads(line)
                if ev.get("type") in ("sleep", "woken"):
                    out.append((datetime.fromisoformat(ev["ts"][:19]), ev["type"]))
            except (json.JSONDecodeError, KeyError, ValueError, AttributeError):
                continue
        day += timedelta(days=1)
    return sorted(out)


def _session_starts(log_dir: Path, start: datetime) -> list[datetime]:
    """その子が動き出した時刻(自律行動・会話の記録の始まり)"""
    out = []
    try:
        names = [f.name for f in log_dir.iterdir() if f.name.endswith("_stream.jsonl")]
    except OSError:
        return out
    for name in names:
        try:
            ts = datetime.strptime(name[:15], "%Y%m%d_%H%M%S")
        except ValueError:
            continue
        if ts >= start:
            out.append(ts)
    return sorted(out)


def _trial_params(char_dir: Path) -> dict:
    """試し算の数字。家の desire_trial.json にあるものだけ、既定を上書きする"""
    p = dict(TRIAL_DEFAULTS)
    try:
        raw = json.loads((char_dir / "config" / "desire_trial.json").read_text(encoding="utf-8")).get(SLEEPY_ID, {})
    except (OSError, json.JSONDecodeError, AttributeError):
        raw = {}
    for k, v in raw.items() if isinstance(raw, dict) else []:
        if k in p and isinstance(v, (int, float)) and v > 0:
            p[k] = float(v)
    return p


def _trial_sleepy(samples: list, p: dict, sleep_marks: list[datetime], body: list[tuple[datetime, str]],
                  sessions: list[datetime]) -> list[float | None]:
    """「眠い」を、相談して決めた案で計算し直す(_trial_rule)。samples と同じ並びの強さを返す"""
    brief = timedelta(minutes=TRIAL_BRIEF_MIN)
    woken = [t for t, k in body if k == "woken"
             and not any(k2 == "sleep" and timedelta(0) <= t2 - t <= brief for t2, k2 in body)]
    events = sorted([(t, "sleep") for t in sleep_marks] + [(t, "sleep") for t, k in body if k == "sleep"]
                    + [(t, "move") for t in woken] + [(t, "move") for t in sessions])
    out: list[float | None] = []
    level, rest_since, night_since, night_dark, prev, i = 0.0, None, None, 0.0, None, 0
    for ts, _, _, sensor in samples:
        ambient = sensor.get("ambient")
        gyro = max((abs(sensor.get(k) or 0) for k in ("gx", "gy", "gz")), default=0)
        known = isinstance(ambient, (int, float))
        dark = known and ambient < TRIAL_DARK
        bright = known and ambient >= TRIAL_BRIGHT
        step_h = (ts - prev).total_seconds() / 3600 if prev else 0.0
        prev = ts
        gap = step_h > 0.5   # 記録が抜けたところ。明るさは分からない
        moved = False
        while i < len(events) and events[i][0] <= ts:
            when, kind = events[i]
            i += 1
            if kind == "move":
                moved = True
                continue
            if rest_since is None:
                rest_since = when
            if night_since is None and (when.hour >= TRIAL_NIGHT_FROM or when.hour < TRIAL_NIGHT_TO):
                night_since, night_dark = when, 0.0
        if night_since is not None and (dark or gap):
            night_dark += step_h
        in_night_sleep = night_since is not None and rest_since is not None and (dark or gap)
        if not in_night_sleep:
            speed = 1.0
            if known and not gap:
                speed = p["dark_x"] if dark and gyro < TRIAL_STILL else p["bright_x"] if bright else 1.0
            level = min(1.0, level + speed * step_h / p["hours"])
        if moved:
            long_night = night_since is not None and (
                night_dark >= TRIAL_NIGHT_DARK_H or (ts - night_since).total_seconds() >= TRIAL_NIGHT_ANY_H * 3600)
            if long_night and not dark:     # 朝
                level, night_since, night_dark, rest_since = 0.0, None, 0.0, None
            elif not dark:                  # 昼の休みから動き出した(暗いまま動いただけなら、まだ休みの続き)
                if rest_since is not None:
                    rest_h = (ts - rest_since).total_seconds() / 3600
                    level *= 1 - min(p["relief_cap"], p["relief_rate"] * rest_h)
                rest_since = None
        out.append(round(level, 3))
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
    ids = list(desires_cfg) + sorted({k for _, _, lv, _ in samples for k in lv} - set(desires_cfg))
    desires = []
    for did in ids:
        d = desires_cfg.get(did, {}) if isinstance(desires_cfg.get(did, {}), dict) else {}
        values = [lv.get(did) for _, _, lv, _ in samples]
        seen = [v for v in values if isinstance(v, (int, float))]
        keywords = [k for k in d.get("keywords", []) if isinstance(k, str)]
        desires.append({
            "id": did, "name": d.get("name_ja", did), "color": d.get("color", "#cab8d9"), "description": d.get("description", ""),
            "hours": d.get("satisfaction_hours"), "keywords": keywords,
            "time_driven": d.get("time_driven", True), "base_level": d.get("base_level"),
            "values": values, "now": seen[-1] if seen else None,
            "full_pct": round(100 * sum(v >= FULL for v in seen) / len(seen)) if seen else None,
            "top_pct": round(100 * sum(top == did for _, top, _, _ in samples) / n) if n else None,
            "mean": round(sum(seen) / len(seen), 2) if seen else None,
            "satisfied": _satisfied_times(memory_db, keywords, start),
            "tool_satisfied": tool.get(did, 0),
        })
        if did == SLEEPY_ID and samples and isinstance(d.get("satisfaction_hours"), (int, float)):
            params = _trial_params(char_dir)
            marks = [datetime.fromisoformat(t) for t in desires[-1]["satisfied"]]
            trial = _trial_sleepy(samples, params, marks, _body_events(char_dir, start, now), _session_starts(log_dir, start))
            got = [v for v in trial if v is not None]
            # 夜(20 時〜2 時)に「おやすみ」を書く直前の眠さ。いまの決まりと試し算で、それぞれの平均
            bed_now, bed_trial = [], []
            for m in marks:
                if not (m.hour >= 20 or m.hour < 2):
                    continue
                near = [i for i, (ts, _, _, _) in enumerate(samples) if timedelta(0) <= m - ts <= timedelta(minutes=12)]
                if near and isinstance(values[near[-1]], (int, float)):
                    bed_now.append(values[near[-1]])
                    bed_trial.append(trial[near[-1]])
            desires[-1]["trial"] = {"values": trial, "rule": _trial_rule(params), "params": params,
                                    "full_pct": round(100 * sum(v >= FULL for v in got) / len(got)) if got else None,
                                    "bed_count": len(bed_now),
                                    "bed_now": round(sum(bed_now) / len(bed_now), 2) if bed_now else None,
                                    "bed_trial": round(sum(bed_trial) / len(bed_trial), 2) if bed_trial else None}

    def _desc(items: object) -> list[str]:
        return [str(i.get("description", "")) for i in items if isinstance(i, dict) and i.get("description")] if isinstance(items, list) else []

    return {
        "from": start.isoformat(timespec="seconds"), "to": now.isoformat(timespec="seconds"), "samples": n,
        "times": [ts.isoformat(timespec="minutes") for ts, _, _, _ in samples],
        "desires": desires,
        "sensor_effects": _desc(cfg.get("sensor_effects")), "cross_effects": _desc(cfg.get("cross_effects")),
        "priority": [p for p in cfg.get("priority", []) if isinstance(p, str)],
    }
