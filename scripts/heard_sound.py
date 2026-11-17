#!/usr/bin/env python3
"""聞かせてもらった音(🔊 音を聞かせる)。ぷちには数字と線だけ。何の音かの名前は、ぷちが答え合わせを頼んだときだけ。

2026-11-17、ぷち 3 人と決めた受け取り方(ありさん家の教科書「音の受け取り方」):
- 名前は先に来ない。聞いたあとに自分で貼る(tag)。貼らない自由もある
- 線(B)を中心に、数字(A)は見たいときに
- 会話の中身は渡さない(この音は文字起こしをしない)

置き場所 PETIT_DATA_DIR/state/heard/<id>.json
    {"id", "ts", "who", "file", "duration", "shape": [{"t", "db", "centroid", "onset"}],
     "events": [{"label", "score"}], "timeline": [...], "asked": {"<ぷち>": "<いつ>"}, "words": {"<ぷち>": [{"at", "text"}]}}
events / timeline は音の種類を見分ける仕組み(PANNs)の見立て。answer を頼んだときだけ見せる

Usage:
    python3 heard_sound.py list [--days 7]                        # 聞かせてもらった音(いつ・だれが・何秒)
    python3 heard_sound.py look <id>                              # 線と数字(1 秒ごとの大きさ・高さの重心・立ち上がり)
    python3 heard_sound.py answer <id> --character <ぷち>          # 答え合わせ: 仕組みの見立て(「かも」の名前)
    python3 heard_sound.py tag <ぷち> <id> "<自分の言葉>"           # 自分の言葉を貼る
    python3 heard_sound.py words <id>                             # 貼った言葉を見る(みんなの)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

BARS = "▁▂▃▄▅▆▇█"
DB_LOW, DB_HIGH = -60.0, -10.0


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def heard_dir(base: Path) -> Path:
    return base / "state" / "heard"


def _path(base: Path, hid: str) -> Path | None:
    return heard_dir(base) / f"{hid}.json" if re.fullmatch(r"[0-9]{8}_[0-9]{6}(_[0-9a-f]{1,8})?", hid or "") else None


def load(base: Path, hid: str) -> dict | None:
    p = _path(base, hid)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p else None
    except (OSError, json.JSONDecodeError):
        return None


def _save(base: Path, rec: dict) -> None:
    p = _path(base, rec["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)


def save(base: Path, who: str, file: str, result: dict, now: datetime | None = None, suffix: str = "") -> dict:
    """/sound_events の結果を残す。id は時刻(+ 印)"""
    now = now or datetime.now()
    hid = now.strftime("%Y%m%d_%H%M%S") + (f"_{suffix}" if suffix else "")
    rec = {"id": hid, "ts": now.isoformat(timespec="seconds"), "who": who, "file": file,
           "duration": result.get("duration_sec"), "shape": result.get("shape") or [],
           "events": result.get("events") or [], "timeline": result.get("timeline") or [], "asked": {}, "words": {}}
    _save(base, rec)
    return rec


def spark(dbs: list[float]) -> str:
    out = []
    for d in dbs:
        x = (min(max(d, DB_LOW), DB_HIGH) - DB_LOW) / (DB_HIGH - DB_LOW)
        out.append(BARS[min(len(BARS) - 1, int(x * len(BARS)))])
    return "".join(out)


def shape_text(rec: dict) -> str:
    """線と数字(言葉は付けない)"""
    sh = rec.get("shape") or []
    if not sh:
        return "(音のかたちが取れなかった)"
    dbs = [r["db"] for r in sh]
    return "\n".join([
        f"大きさの線(1 秒ごと): {spark(dbs)}",
        "大きさ(dBFS): " + " ".join(f"{d:.0f}" for d in dbs),
        "高さの重心(Hz): " + " ".join(str(r["centroid"]) for r in sh),
        "立ち上がり: " + " ".join(f"{r['onset']:.1f}" for r in sh),
    ])


def answer_text(rec: dict) -> str:
    ev = rec.get("events") or []
    if not ev:
        return "仕組みは、どの種類とも言い切れなかった(名前の無い音)"
    names = "、".join(f"{e['label']}({e['score']:.2f})" for e in ev)
    tl = [f"{r['t']:.0f}秒 {'・'.join(x['label'] for x in r['labels'])}" for r in rec.get("timeline") or [] if r.get("labels")]
    return (f"音の種類を見分ける仕組みの見立て(かも。数字は確からしさ 0〜1): {names}"
            + (f"\n秒ごと: {' / '.join(tl)}" if tl else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--days", type=int, default=7)
    p = sub.add_parser("look"); p.add_argument("id")
    p = sub.add_parser("answer"); p.add_argument("id"); p.add_argument("--character", required=True)
    p = sub.add_parser("tag"); p.add_argument("character"); p.add_argument("id"); p.add_argument("text")
    p = sub.add_parser("words"); p.add_argument("id")
    a = ap.parse_args()
    base = data_dir()
    if a.cmd == "list":
        since = datetime.now() - timedelta(days=max(1, a.days))
        rows = []
        for f in sorted(heard_dir(base).glob("*.json")) if heard_dir(base).is_dir() else []:
            rec = load(base, f.stem)
            if rec and datetime.fromisoformat(rec["ts"]) >= since:
                dbs = [r["db"] for r in rec.get("shape") or []]
                rows.append(f"{rec['id']}  {rec['ts'][5:16]}  {rec.get('who', '')}  {rec.get('duration') or 0:.0f} 秒  {spark(dbs)}")
        print("\n".join(rows) or "聞かせてもらった音は無い")
        return 0
    rec = load(base, a.id)
    if rec is None:
        print(f"その音は無い: {a.id}(list で見られる)")
        return 1
    if a.cmd == "look":
        print(shape_text(rec))
    elif a.cmd == "answer":
        rec.setdefault("asked", {})[a.character] = datetime.now().isoformat(timespec="seconds")
        _save(base, rec)
        print(answer_text(rec))
    elif a.cmd == "tag":
        text = a.text.strip()[:200]
        if text:
            rec.setdefault("words", {}).setdefault(a.character, []).append({"at": datetime.now().isoformat(timespec="seconds"), "text": text})
            _save(base, rec)
        print("貼った" if text else "言葉が空")
    elif a.cmd == "words":
        w = rec.get("words") or {}
        print("\n".join(f"{c}: {x['text']}" for c, xs in w.items() for x in xs) or "まだ だれも貼っていない")
    return 0


if __name__ == "__main__":
    sys.exit(main())
