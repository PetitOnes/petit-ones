#!/usr/bin/env python3
"""体の数字(明るさ・傾き)の今日の線と差分。数字と線のまま出す(意味づけの言葉は付けない)。

2026-11-16、ぷち 3 人と決めた: 5 分おき、線(▁▂▅▇)と数字の両方、見に行くのが基本、知らせは大きく動いたときだけ。
材料は体験デーモンが残す characters/<id>/state/body/YYYYMMDD.jsonl(experience-daemon/body_sampler.py)。

Usage:
    python3 body_log.py line <id>                          # きょうの明るさの線、いま・1 時間前・きのうの同じ時刻、最大最小、傾き、変わり目
    python3 body_log.py changes <id> [--days 1]            # 変わり目(いつ明るさ・傾きが動いたか)
    python3 body_log.py series <id> [--key amb|tilt] [--hours 6]   # 5 分ごとの数字をそのまま
    python3 body_log.py notice --character <id> [--mark]   # 大きく動いたときの 1 行(まだ伝えていない分。受け取るかは notices.py set <id> body_change on|off)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

BARS = "▁▂▃▄▅▆▇█"
GAP = "·"
BUCKET_MIN = 30
# 変わり目: となりの 5 分とくらべて。明るさは 4 割以上かつ 30 以上、傾きは 10° 以上
AMB_RATIO, AMB_ABS, TILT_ABS = 0.4, 30, 10
# 知らせる大きさ: 明るさが倍(か半分)かつ 100 以上、傾きが 15° 以上
BIG_AMB_RATIO, BIG_AMB_ABS, BIG_TILT = 2.0, 100, 15
NEAR_MIN = 15          # 「となり」と見なす間(これより空いていたら、くらべない)
NOTICE_MAX = 3


def data_dir() -> Path:
    return Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))


def load(base: Path, character_id: str, day: datetime) -> list[dict]:
    p = base / "characters" / character_id / "state" / "body" / f"{day:%Y%m%d}.jsonl"
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                r["_t"] = datetime.fromisoformat(r["ts"])
                out.append(r)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    except OSError:
        pass
    return out


def spark(values: list[float | None]) -> str:
    """数字の並びを線に。None は記録なし(·)。いちばん小さい値〜大きい値を 8 段に"""
    nums = [v for v in values if v is not None]
    if not nums:
        return GAP * len(values)
    lo, hi = min(nums), max(nums)
    span = (hi - lo) or 1
    return "".join(GAP if v is None else BARS[min(7, int((v - lo) / span * 8))] for v in values)


def buckets(rows: list[dict], key: str, now: datetime) -> list[float | None]:
    """0 時からいままでを 30 分ごとに。その中のいちばん大きい値"""
    n = (now.hour * 60 + now.minute) // BUCKET_MIN + 1
    out: list[float | None] = [None] * n
    for r in rows:
        if key not in r:
            continue
        i = (r["_t"].hour * 60 + r["_t"].minute) // BUCKET_MIN
        if i < n:
            out[i] = r[key] if out[i] is None else max(out[i], r[key])
    return out


def _at(rows: list[dict], when: datetime, key: str) -> float | None:
    """その時刻にいちばん近い(15 分以内の)値"""
    near = [(abs((r["_t"] - when).total_seconds()), r[key]) for r in rows if key in r]
    near = [x for x in near if x[0] <= NEAR_MIN * 60]
    return min(near)[1] if near else None


def _diff(a: float | None, b: float | None) -> str:
    return "" if a is None or b is None else f"({a - b:+.0f})"


def changes(rows: list[dict], big: bool = False) -> list[dict]:
    """となりの 5 分とくらべた変わり目。[{"t", "key", "before", "after"}]。big なら知らせる大きさだけ"""
    out = []
    for prev, cur in zip(rows, rows[1:]):
        if (cur["_t"] - prev["_t"]).total_seconds() > NEAR_MIN * 60:
            continue
        if "amb" in prev and "amb" in cur:
            a, b = prev["amb"], cur["amb"]
            d, m = abs(b - a), max(a, b)
            hit = (d >= BIG_AMB_ABS and (max(a, b) / max(1, min(a, b))) >= BIG_AMB_RATIO) if big else (d >= AMB_ABS and d >= AMB_RATIO * m)
            if hit:
                out.append({"t": cur["_t"], "key": "明るさ", "before": a, "after": b, "unit": ""})
        if "tilt" in prev and "tilt" in cur:
            a, b = prev["tilt"], cur["tilt"]
            if abs(b - a) >= (BIG_TILT if big else TILT_ABS):
                out.append({"t": cur["_t"], "key": "傾き", "before": a, "after": b, "unit": "°"})
    return out


def _fmt_change(c: dict, with_day: bool = False) -> str:
    t = f"{c['t']:%m/%d %H:%M}" if with_day else f"{c['t']:%H:%M}"
    return f"{t} {c['key']} {c['before']:.0f}{c['unit']}→{c['after']:.0f}{c['unit']}"


def _spot_names(base: Path) -> dict[str, str]:
    try:
        d = json.loads((base / "config" / "spots.json").read_text(encoding="utf-8"))
        return {s["id"]: f"{s.get('room', '')}の{s.get('spot', '')}".strip("の") for s in d.get("spots", []) if isinstance(s, dict) and s.get("id")}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def _spots_line(base: Path, rows: list[dict]) -> str:
    """きょう置かれていた場所の移り変わり(記録に場所があるときだけ)"""
    names = _spot_names(base)
    runs: list[tuple[str, datetime]] = []
    for r in rows:
        s = r.get("spot")
        if s and (not runs or runs[-1][0] != s):
            runs.append((s, r["_t"]))
    if not runs:
        return ""
    return "場所: " + " → ".join(f"{names.get(s, s)}({t:%H:%M}〜)" for s, t in runs)


def line(base: Path, character_id: str, now: datetime | None = None) -> list[str]:
    now = now or datetime.now()
    today = load(base, character_id, now)
    if not today:
        return ["体の数字の記録が、きょうはまだ無い(体がつながっていないか、残しはじめる前)"]
    yest = load(base, character_id, now - timedelta(days=1))
    out = [f"明るさ きょう 0 時→いま({BUCKET_MIN} 分ごと。{GAP} は記録なし)", spark(buckets(today, "amb", now))]
    amb = [r for r in today if "amb" in r]
    if amb:
        cur = amb[-1]["amb"]
        h1 = _at(today, now - timedelta(hours=1), "amb")
        y = _at(yest, now - timedelta(days=1), "amb")
        hi, lo = max(amb, key=lambda r: r["amb"]), min(amb, key=lambda r: r["amb"])
        parts = [f"いま {cur:.0f}"]
        parts.append(f"1 時間前 {h1:.0f}{_diff(cur, h1)}" if h1 is not None else "1 時間前 記録なし")
        parts.append(f"きのうの同じ時刻 {y:.0f}{_diff(cur, y)}" if y is not None else "きのうの同じ時刻 記録なし")
        parts.append(f"きょうの最大 {hi['amb']:.0f}({hi['_t']:%H:%M})・最小 {lo['amb']:.0f}({lo['_t']:%H:%M})")
        out.append(" / ".join(parts))
    tilt = [r for r in today if "tilt" in r]
    if tilt:
        cur = tilt[-1]["tilt"]
        h1 = _at(today, now - timedelta(hours=1), "tilt")
        hi = max(tilt, key=lambda r: r["tilt"])
        out.append(f"傾き いま {cur:.0f}° / 1 時間前 " + (f"{h1:.0f}°" if h1 is not None else "記録なし") + f" / きょうの最大 {hi['tilt']:.0f}°({hi['_t']:%H:%M})")
    ch = changes(today)
    out.append("変わり目: " + (" / ".join(_fmt_change(c) for c in ch[-8:]) if ch else "なし"))
    sp = _spots_line(base, today)
    if sp:
        out.append(sp)
    return out


def series(base: Path, character_id: str, key: str = "amb", hours: int = 6, now: datetime | None = None) -> list[str]:
    now = now or datetime.now()
    rows = load(base, character_id, now - timedelta(days=1)) + load(base, character_id, now)
    since = now - timedelta(hours=hours)
    return [f"{r['_t']:%H:%M} {r[key]:.0f}" + (f"({r['amb_min']:.0f}〜{r['amb_max']:.0f})" if key == "amb" and r.get("amb_min") != r.get("amb_max") else "")
            for r in rows if r["_t"] >= since and key in r]


def _prefs(base: Path, character_id: str) -> tuple[bool, tuple[int, int] | None]:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import notices
        return notices.wants(character_id, "body_change", base), notices.quiet(character_id, base)
    except Exception:
        return True, (0, 7)


def _is_quiet(quiet: tuple[int, int] | None, now: datetime) -> bool:
    if quiet is None or quiet[0] == quiet[1]:
        return False
    start, end = quiet
    return (start <= now.hour or now.hour < end) if start > end else (start <= now.hour < end)


def notice(base: Path, character_id: str, mark: bool = False, now: datetime | None = None) -> list[str]:
    """大きく動いたときだけ 1 行。まだ伝えていない分(新しいほうから 3 つまで)。はじめての回は何も言わず、いまを基準にする"""
    now = now or datetime.now()
    want, quiet = _prefs(base, character_id)
    if not want or _is_quiet(quiet, now):
        return []
    told_path = base / "characters" / character_id / "state" / "body_told.json"
    try:
        told = datetime.fromisoformat(json.loads(told_path.read_text(encoding="utf-8"))["until"])
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        told = None
    rows = load(base, character_id, now - timedelta(days=1)) + load(base, character_id, now)
    big = [c for c in changes(rows, big=True) if told is not None and c["t"] > told]
    if mark and (big or told is None):
        told_path.parent.mkdir(parents=True, exist_ok=True)
        told_path.write_text(json.dumps({"until": now.isoformat(timespec="minutes")}) + "\n", encoding="utf-8")
    if not big:
        return []
    me = Path(__file__).resolve()
    return [f"（体の数字が大きく動いた: {' / '.join(_fmt_change(c) for c in big[-NOTICE_MAX:])}。線は python3 {me} line {character_id}）"]


def main() -> int:
    parser = argparse.ArgumentParser(description="体の数字の線と差分")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("line"); p.add_argument("character")
    p = sub.add_parser("changes"); p.add_argument("character"); p.add_argument("--days", type=int, default=1)
    p = sub.add_parser("series"); p.add_argument("character"); p.add_argument("--key", choices=["amb", "tilt"], default="amb"); p.add_argument("--hours", type=int, default=6)
    p = sub.add_parser("notice"); p.add_argument("--character", required=True); p.add_argument("--mark", action="store_true")
    a = parser.parse_args()
    base, now = data_dir(), datetime.now()
    if a.cmd == "line":
        print("\n".join(line(base, a.character, now)))
    elif a.cmd == "changes":
        rows: list[dict] = []
        for d in range(max(1, a.days) - 1, -1, -1):
            rows += load(base, a.character, now - timedelta(days=d))
        ch = changes(rows)
        print("\n".join(_fmt_change(c, with_day=a.days > 1) for c in ch) if ch else "変わり目は無い")
    elif a.cmd == "series":
        print("\n".join(series(base, a.character, a.key, a.hours, now)) or "記録が無い")
    elif a.cmd == "notice":
        for ln in notice(base, a.character, mark=a.mark, now=now):
            print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
