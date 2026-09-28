#!/usr/bin/env python3
"""token_log.jsonl の cost_usd を「1回ぶん」に直す。

2026-09 から、`claude --resume` の result.total_cost_usd が **セッションの累計**で返るようになった
(それまでは 1 回ぶん)。集計が cost_usd をそのまま足していたので、9 月ぶんが過大になっていた(2026-09-28 発見)。

直し方: 2026-09-19 以降の行で、トークン数からの概算(est)と比べて cost が 1.15 倍を超える行は累計の疑い。同じ (character, source) の
直近 8 行の cost のうち、引いた差が est にいちばん近いもの(または引かない)を選ぶ。new の行と、est と合っている行はそのまま。

使い方: python3 cost_correct.py            → 月別・キャラ別の 元の合計 / 直した合計 を表示
        from cost_correct import load_corrected  → [{timestamp, date, character, source, cost, cost_raw, fixed}]"""
import collections
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
TOKEN_LOG = Path.home() / "petit_claude" / "token_logs" / "token_log.jsonl"
SUSPECT_RATIO = 1.15
CUMULATIVE_SINCE = "2026-09-19"   # この日から total_cost_usd が累計になった(日別の合計が跳ねた最初の日)。それ以前は直さない(Opus の回を誤って引かないため)
def est(ev):
    return ((ev.get("input") or 0) * 3 + (ev.get("output") or 0) * 15 + (ev.get("cache_creation") or 0) * 3.75 + (ev.get("cache_read") or 0) * 0.30) / 1e6
def load_corrected(path=TOKEN_LOG):
    rows = []
    with Path(path).open(encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
            dt = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00")).astimezone(JST)
        except (json.JSONDecodeError, KeyError, ValueError, AttributeError):
            continue
        ev["_dt"] = dt
        rows.append(ev)
    rows.sort(key=lambda e: e["_dt"])
    recent = collections.defaultdict(list)   # (character, source) → 直近の cost_raw
    out = []
    for ev in rows:
        e = est(ev); raw = ev.get("cost_usd") or 0
        key = (ev.get("character", "unknown"), ev.get("source", "unknown"))
        cost, fixed = raw, False
        if raw == 0: cost = e
        elif ev["_dt"].strftime("%Y-%m-%d") >= CUMULATIVE_SINCE and ev.get("session_type") != "new" and e > 0 and raw / e > SUSPECT_RATIO:
            # 累計の疑い: 直近の cost を引いた差のうち、概算にいちばん近いものを選ぶ(引かない も候補)
            cands = [raw] + [raw - c for c in recent[key][-8:] if 0 < raw - c]
            best = min(cands, key=lambda c: abs(math.log(max(c, 1e-6) / e)))
            if best != raw: cost, fixed = best, True
        if raw: recent[key].append(raw)
        out.append({"timestamp": ev["timestamp"], "dt": ev["_dt"], "date": ev["_dt"].strftime("%Y-%m-%d"), "character": key[0], "source": key[1],
                    "cost": cost, "cost_raw": raw if raw else e, "est": e, "fixed": fixed, "session_type": ev.get("session_type")})
    return out
if __name__ == "__main__":
    rows = load_corrected()
    def table(keyf, title):
        a = collections.defaultdict(lambda: [0.0, 0.0, 0, 0])
        for r in rows:
            k = keyf(r); a[k][0] += r["cost_raw"]; a[k][1] += r["cost"]; a[k][2] += 1; a[k][3] += r["fixed"]
        print(f"\n## {title}\n| | 元の合計 $ | 直した合計 $ | 差 $ | 行数 | 直した行 |\n|---|---|---|---|---|---|")
        for k in sorted(a): v = a[k]; print(f"| {k} | {v[0]:.2f} | {v[1]:.2f} | {v[0]-v[1]:.2f} | {v[2]} | {v[3]} |")
    table(lambda r: r["date"][:7], "月別")
    table(lambda r: r["character"], "キャラ別(全期間)")
    table(lambda r: r["source"], "種類別(全期間)")
    sept = [r for r in rows if r["date"] >= "2026-08-26"]
    a = collections.defaultdict(lambda: [0.0, 0.0])
    for r in sept: a[r["date"]][0] += r["cost_raw"]; a[r["date"]][1] += r["cost"]
    print("\n## 日別(8/26〜)\n| 日 | 元 $ | 直した $ |\n|---|---|---|")
    for d in sorted(a): print(f"| {d} | {a[d][0]:.2f} | {a[d][1]:.2f} |")
    first = next((r for r in rows if r["fixed"]), None)
    print("\n最初に直した行:", first and (first["timestamp"], first["character"], first["source"]))
