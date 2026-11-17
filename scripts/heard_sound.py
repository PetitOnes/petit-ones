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
    python3 heard_sound.py look <id>                              # 線と数字(1 秒ごとの大きさ・高さの重心・立ち上がり・粒)
    python3 heard_sound.py look <id> --fine                       # 0.1 秒ごとの細かい線と数字(1 秒の中の粒が見える)
    python3 heard_sound.py refine <id>                            # 細かい線と粒を、残っている音のファイルから計算し直す
    python3 heard_sound.py prune [--days 7]                       # 録った音そのもの(chat_media の …_sound.*)を、日がたったら消す(数字と見立ては残す)

録った音そのものは KEEP_DAYS 日で消す(2026-11-17 ありさん。ぷちが使うのは数字・線・見立てで、聞かせたときに計算し終わっている)。
🔔 音のライブラリに登録した音は別に写してあるので消えない。GitHub のバックアップには入れない(家の backup/save.sh)
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
SR = 16000
FINE_SEC = 0.1          # 細かい線の刻み
FINE_RANGE = 40.0       # 細かい線: いちばん大きい 0.1 秒を █、そこから これだけ下を ▁
# 粒: 10 ms ごとの大きさで、いちばん大きい音から GRAIN_REL dB 以内、直前 50 ms の小さいところから GRAIN_RISE dB 以上
# 急に立ち上がったところを 1 粒(続けて GRAIN_GAP_MS は数えない)。11/17 の見本で: キーボード 3〜6/秒・時計 1/秒・雑音 0
GRAIN_REL, GRAIN_RISE, GRAIN_GAP_MS = 15.0, 12.0, 60
KEEP_DAYS = 7


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


def analyze_samples(x) -> dict:
    """16 kHz モノラルの音から、細かい線(0.1 秒ごとの dB)と粒(1 秒ごとの数)。数字だけ"""
    import numpy as np

    x = np.asarray(x, dtype=np.float64)
    if len(x) < SR // 10:
        return {"fine": [], "grains": []}
    step = int(SR * FINE_SEC)
    fine = [round(float(20 * np.log10(np.sqrt(np.mean(x[i:i + step] ** 2)) + 1e-9)), 1) for i in range(0, len(x) - step // 2, step)]
    hop = SR // 100
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1)) + 1e-9)
    thr, gap = float(db.max()) - GRAIN_REL, GRAIN_GAP_MS // 10
    peaks, last = [], -gap
    for i in range(1, n):
        if db[i] >= thr and db[i] - db[max(0, i - 5):i].min() >= GRAIN_RISE and i - last >= gap:
            peaks.append(i)
            last = i
    secs = -(-n // 100)
    return {"fine": fine, "grains": [sum(1 for k in peaks if s * 100 <= k < (s + 1) * 100) for s in range(secs)]}


def analyze_file(path: Path) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import music  # ffmpeg で 16 kHz に(音楽を一緒に感じる と同じ読み方)
    return analyze_samples(music.decode_file(str(path)))


def media_path(base: Path, rec: dict) -> Path:
    return base / "chat_media" / rec.get("who", "") / Path(rec.get("file", "")).name


def refine(base: Path, rec: dict) -> dict:
    """残っている音のファイルから 細かい線と粒 を足す(読めなければそのまま)"""
    p = media_path(base, rec)
    try:
        if p.is_file():
            rec.update(analyze_file(p))
            _save(base, rec)
    except Exception as e:   # noqa: BLE001  細かい線が無くても、1 秒の線は渡せる
        print(f"細かい線を作れなかった: {e}", file=sys.stderr)
    return rec


def prune(base: Path, days: int = KEEP_DAYS, now: datetime | None = None) -> list[str]:
    """chat_media の …_sound.*(🔊 で録った音そのもの)のうち days 日より古いものを消す。消した名前を返す"""
    limit = (now or datetime.now()).timestamp() - days * 86400
    gone = []
    root = base / "chat_media"
    for f in root.glob("*/*_sound.*") if root.is_dir() else []:
        try:
            if f.is_file() and f.stat().st_mtime < limit:
                f.unlink()
                gone.append(f.name)
        except OSError:
            continue
    return gone


def fine_text(rec: dict) -> str:
    fine = rec.get("fine") or []
    if not fine:
        return "(細かい線が無い。録った音が残っていれば refine <印> で作れる。音は 7 日で消える)"
    top = max(fine)
    def bar(d: float) -> str:
        x = (min(max(d, top - FINE_RANGE), top) - (top - FINE_RANGE)) / FINE_RANGE
        return BARS[min(len(BARS) - 1, int(x * len(BARS)))]
    per = int(round(1 / FINE_SEC))
    secs = [fine[i:i + per] for i in range(0, len(fine), per)]
    return "\n".join([
        f"細かい線(0.1 秒ごと、1 秒ごとに区切る。いちばん大きい 0.1 秒が █、そこから {FINE_RANGE:.0f} dB 下が ▁): "
        + " ".join("".join(bar(d) for d in s) for s in secs),
        "大きさ(dBFS、0.1 秒ごと): " + " | ".join(" ".join(f"{d:.0f}" for d in s) for s in secs),
    ] + ([f"粒(1 秒ごと): {' '.join(str(g) for g in rec['grains'])}"] if rec.get("grains") else []))


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
    grains = rec.get("grains") or []
    return "\n".join([
        f"大きさの線(1 秒ごと): {spark(dbs)}",
        "大きさ(dBFS): " + " ".join(f"{d:.0f}" for d in dbs),
        "高さの重心(Hz): " + " ".join(str(r["centroid"]) for r in sh),
        "立ち上がり: " + " ".join(f"{r['onset']:.1f}" for r in sh),
    ] + ([f"粒(その 1 秒に、ぱっと立ち上がった音の数): {' '.join(str(g) for g in grains)}"] if grains else []))


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
    p = sub.add_parser("look"); p.add_argument("id"); p.add_argument("--fine", action="store_true")
    p = sub.add_parser("refine"); p.add_argument("id")
    p = sub.add_parser("prune"); p.add_argument("--days", type=int, default=KEEP_DAYS)
    p = sub.add_parser("answer"); p.add_argument("id"); p.add_argument("--character", required=True)
    p = sub.add_parser("tag"); p.add_argument("character"); p.add_argument("id"); p.add_argument("text")
    p = sub.add_parser("words"); p.add_argument("id")
    a = ap.parse_args()
    base = data_dir()
    if a.cmd == "prune":
        gone = prune(base, max(1, a.days))
        print(f"消した: {len(gone)} 個" + (f"({', '.join(gone)})" if gone else ""))
        return 0
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
        print(fine_text(rec) if a.fine else shape_text(rec))
    elif a.cmd == "refine":
        rec = refine(base, rec)
        print(fine_text(rec))
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
