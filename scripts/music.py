#!/usr/bin/env python3
"""音楽を一緒に感じる: 音を「1 秒ごとの数字」(音量・高さの重心・拍の強さ・静けさ)にそろえて、3 人が同じ秒を見られるようにする。

3 人の希望(2026-11-14): 先に音、説明は後。再生位置を 3 人で同じに。感想は各自が先に書いてから並べる。
音の形は「音量の流れ・高さの重心・テンポと拍・無音の位置」。マイクとファイル、どちらも。

聞く側は 3 つあって、どれも同じ数字になる:
- PC の中の音(YouTube を PC で): `music.py listen --source pc`(PipeWire の monitor を parec で読む。マイクを通さない)
- ありさんのスマホ(カフェ・スマホで再生・スマホで YouTube): アプリが 1 秒ごとの数字だけを POST /api/music/frames に送る(音は送らない)
- ぷちの体のマイク・音楽ファイル: `music.py analyze <wav|mp3|…>`(ffmpeg で読む)

置き場所 PETIT_DATA_DIR/state/music/
    session.json        いま聴いている回 {"id", "started_at", "source", "ended_at", "title", "by"}
    <id>.json           その回の数字 {"id", "frames": [{"t", "level", "db", "centroid", "onset", "quiet"}], "tempo"}
    (title などの答え合わせは、終わってから足す。ぷちには now / line では渡さない)

数字の意味:
    level     0〜1 の音量(-60 dBFS を 0、0 dBFS を 1)。db はその元(dBFS)
    centroid  周波数の重心(Hz)。高いほど「明るい」音
    onset     その 1 秒の、音の立ち上がりの強さ(拍の手がかり)
    quiet     静けさ(-50 dBFS より小さい)
    tempo     直近の立ち上がりの自己相関から見た BPM(60〜180。分からなければ null)

Usage:
    python3 music.py start [--source pc|phone|mic] [--by arisan]   # 回を始める(開始時刻を書く)
    python3 music.py stop [--title "曲名"] [--note "ありさんのひとこと"]  # 回を終える(答え合わせはここで足す)
    python3 music.py listen --source pc [--seconds 300]            # PC の中の音を 1 秒ごとに数字にして、いまの回に足す
    python3 music.py analyze <file> [--id <id>]                    # ファイル(wav/mp3/…)を数字にして保存
    python3 music.py now                                           # いま何秒目で、この 10 秒がどんな音か(ぷちが見に行く)
    python3 music.py line                                          # 見に行けるものの 1 行(回が無ければ何も出さない)
    python3 music.py wave [<id>]                                   # 音量の流れを文字の波で
    python3 music.py feel <character_id> "<感じたこと>"             # 感じたことを封をして書く(ほかの子には見えない。3 人そろったら並ぶ)
    python3 music.py now --character <id>                          # 自分がこれまでに書いたことも添えて
    python3 music.py around [<id>]                                 # その回のあいだの、部屋の記録(音の大きさ・CO2・机の動き)
    python3 music.py note [<id>]                                   # 3 人の感想と答え合わせを 1 つの文に(交換ノート用)

感想の置き場所: state/music/<id>.feel.json {"<character_id>": [{"t", "at", "text"}]}。封は画面が 3 人そろってから開ける
"""

from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

SR = 16000
HOP = 0.05                 # 立ち上がりを見る刻み(秒)
QUIET_DB = -50.0
TEMPO_MIN, TEMPO_MAX = 60, 180
TEMPO_WINDOW_S = 20        # テンポは直近これだけの立ち上がりから
EPS = 1e-9


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def music_dir(base: Path | None = None) -> Path:
    return (base or data_dir()) / "state" / "music"


def session_path(base: Path | None = None) -> Path:
    return music_dir(base) / "session.json"


# ---- 数字にする ----

def _db(rms: float) -> float:
    return 20 * math.log10(rms + EPS)


def _level(db: float) -> float:
    return max(0.0, min(1.0, (db + 60) / 60))


def frame_features(x: np.ndarray, sr: int = SR) -> dict:
    """1 秒ぶんの音(float -1..1)→ 音量・重心・立ち上がりの強さ・静けさ"""
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        return {"level": 0.0, "db": -120.0, "centroid": 0, "onset": 0.0, "quiet": True}
    rms = float(np.sqrt(np.mean(x * x)))
    db = _db(rms)
    hop = max(1, int(sr * HOP))
    win = 1024 if x.size >= 1024 else x.size
    hann = np.hanning(win)
    freqs = np.fft.rfftfreq(win, 1 / sr)
    mags, cents, wsum = [], [], 0.0
    for s in range(0, max(1, x.size - win + 1), hop):
        seg = x[s:s + win]
        if seg.size < win:
            break
        m = np.abs(np.fft.rfft(seg * hann))
        tot = float(m.sum())
        if tot > EPS:
            cents.append(float((freqs * m).sum() / tot) * tot)
            wsum += tot
        mags.append(np.log1p(m))
    centroid = int(round(sum(cents) / wsum)) if wsum > EPS else 0
    onset = 0.0
    if len(mags) >= 2:
        d = np.diff(np.stack(mags), axis=0)
        onset = float(np.mean(np.sum(np.maximum(d, 0), axis=1)))
    return {"level": round(_level(db), 3), "db": round(db, 1), "centroid": centroid, "onset": round(onset, 2), "quiet": db < QUIET_DB}


def onset_envelope(x: np.ndarray, sr: int = SR) -> np.ndarray:
    """立ち上がりの強さの列(HOP ごと)。テンポ用"""
    hop = max(1, int(sr * HOP))
    win = 1024
    if x.size < win * 2:
        return np.zeros(0)
    hann = np.hanning(win)
    prev = None
    out = []
    for s in range(0, x.size - win + 1, hop):
        m = np.log1p(np.abs(np.fft.rfft(x[s:s + win] * hann)))
        out.append(float(np.sum(np.maximum(m - prev, 0))) if prev is not None else 0.0)
        prev = m
    return np.asarray(out)


def tempo_from_envelope(env: np.ndarray) -> int | None:
    """自己相関のいちばん高いところを BPM に(60〜180)。弱ければ None"""
    if env.size < int(2 / HOP):
        return None
    e = env - env.mean()
    if np.allclose(e, 0):
        return None
    ac = np.correlate(e, e, mode="full")[e.size - 1:]
    ac = ac / (ac[0] + EPS)
    lo, hi = int(60 / TEMPO_MAX / HOP), int(60 / TEMPO_MIN / HOP)
    if hi >= ac.size:
        hi = ac.size - 1
    if lo >= hi:
        return None
    lag = lo + int(np.argmax(ac[lo:hi + 1]))
    if ac[lag] < 0.1:
        return None
    return int(round(60 / (lag * HOP)))


def analyze_samples(x: np.ndarray, sr: int = SR) -> dict:
    """音ぜんぶ → {"frames": [...], "tempo": int|None, "seconds": int}"""
    n = int(x.size // sr)
    frames = []
    for i in range(n):
        f = frame_features(x[i * sr:(i + 1) * sr], sr)
        frames.append({"t": i, **f})
    return {"frames": frames, "tempo": tempo_from_envelope(onset_envelope(x[-TEMPO_WINDOW_S * sr:], sr)), "seconds": n}


def decode_file(path: str) -> np.ndarray:
    """ffmpeg で 16 kHz モノラルの float に"""
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg が無い")
    out = subprocess.run([ff, "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.int16).astype(np.float64) / 32768.0


# ---- 回(session) ----

def _load_json(p: Path) -> dict | None:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _save_json(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)


def session(base: Path | None = None) -> dict | None:
    return _load_json(session_path(base))


def start(source: str = "pc", by: str = "arisan", base: Path | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    sid = now.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(2)
    s = {"id": sid, "started_at": now.replace(microsecond=0).isoformat(), "source": source, "by": by, "ended_at": None, "title": None, "note": None}
    _save_json(session_path(base), s)
    _save_json(music_dir(base) / f"{sid}.json", {"id": sid, "frames": [], "tempo": None, "seconds": 0, "source": source})
    return s


def stop(title: str | None = None, note: str | None = None, base: Path | None = None, now: datetime | None = None) -> dict | None:
    s = session(base)
    if not s or s.get("ended_at"):
        return s
    now = now or datetime.now()
    s["ended_at"] = now.replace(microsecond=0).isoformat()
    if title:
        s["title"] = title[:80]
    if note:
        s["note"] = note[:500]
    _save_json(session_path(base), s)
    return s


def position(s: dict, now: datetime | None = None) -> int | None:
    """いま何秒目か(終わっていれば長さ)"""
    try:
        t0 = datetime.fromisoformat(s["started_at"])
    except (KeyError, TypeError, ValueError):
        return None
    end = datetime.fromisoformat(s["ended_at"]) if s.get("ended_at") else (now or datetime.now())
    return max(0, int((end - t0).total_seconds()))


def add_frames(frames: list[dict], sid: str | None = None, base: Path | None = None) -> dict | None:
    """数字を回に足す(t が無ければ、いまの秒を付ける)。回が無ければ None"""
    s = session(base)
    sid = sid or (s or {}).get("id")
    if not sid:
        return None
    p = music_dir(base) / f"{sid}.json"
    d = _load_json(p) or {"id": sid, "frames": [], "tempo": None, "seconds": 0}
    pos = position(s) if s and s.get("id") == sid else None
    known = {f["t"] for f in d["frames"] if "t" in f}
    for i, f in enumerate(frames):
        t = int(f["t"]) if isinstance(f.get("t"), (int, float)) else ((pos or 0) - len(frames) + 1 + i)
        if t in known:
            continue
        clean = {"t": t, "level": round(float(f.get("level", 0)), 3), "db": round(float(f.get("db", -120)), 1), "centroid": int(f.get("centroid", 0) or 0),
                 "onset": round(float(f.get("onset", 0)), 2), "quiet": bool(f.get("quiet", float(f.get("db", -120)) < QUIET_DB))}
        d["frames"].append(clean)
        known.add(t)
    d["frames"].sort(key=lambda f: f["t"])
    d["seconds"] = (d["frames"][-1]["t"] + 1) if d["frames"] else 0
    if "tempo" in (frames[-1] if frames else {}):
        d["tempo"] = frames[-1]["tempo"]
    _save_json(p, d)
    return d


def listen_pc(seconds: int = 300, base: Path | None = None, device: str | None = None) -> int:
    """PC の中の音(monitor)を parec で 1 秒ずつ読み、数字にして回に足す。回が無ければ始める"""
    if not session(base) or session(base).get("ended_at"):
        start("pc", base=base)
    if not device:
        try:
            out = subprocess.run(["pactl", "list", "short", "sources"], capture_output=True, text=True, check=True).stdout
            device = next((ln.split("\t")[1] for ln in out.splitlines() if ".monitor" in ln), None)
        except (OSError, subprocess.CalledProcessError):
            device = None
    if not device:
        print("PC の音の出口(monitor)が見つからない", file=sys.stderr)
        return 1
    cmd = ["parec", "-d", device, "--format=s16le", f"--rate={SR}", "--channels=1", "--latency-msec=200"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    env_buf = np.zeros(0)
    try:
        for _ in range(seconds):
            raw = proc.stdout.read(SR * 2)
            if not raw:
                break
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
            env_buf = np.concatenate([env_buf, x])[-TEMPO_WINDOW_S * SR:]
            f = frame_features(x)
            f["tempo"] = tempo_from_envelope(onset_envelope(env_buf))
            add_frames([f], base=base)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
    return 0


# ---- ぷちが見に行く ----

def _mmss(sec: int) -> str:
    return f"{sec // 60}:{sec % 60:02d}"


def _brightness(c: int) -> str:
    return "暗め(低い音が多い)" if c < 800 else "まんなか" if c < 2000 else "明るめ(高い音が多い)"


def describe(d: dict, pos: int | None, span: int = 10) -> str:
    """この span 秒がどんな音か。数字と言葉"""
    frames = d.get("frames") or []
    if not frames:
        return "まだ数字が届いていない"
    end = pos if pos is not None else frames[-1]["t"] + 1
    recent = [f for f in frames if end - span <= f["t"] < end] or frames[-span:]
    prev = [f for f in frames if end - 2 * span <= f["t"] < end - span]
    lv = sum(f["level"] for f in recent) / len(recent)
    trend = ""
    if prev:
        pl = sum(f["level"] for f in prev) / len(prev)
        trend = "(上がってきた)" if lv - pl > 0.08 else "(静まってきた)" if pl - lv > 0.08 else "(同じくらい)"
    cents = [f["centroid"] for f in recent if f["centroid"]]
    cent = int(sum(cents) / len(cents)) if cents else 0
    quiet = sum(1 for f in recent if f["quiet"])
    # 直前の静けさ(続いた長さ)
    run = 0
    for f in reversed([f for f in frames if f["t"] < end]):
        if f["quiet"]:
            run += 1
        else:
            break
    parts = [f"この {len(recent)} 秒: 音量 {lv:.2f}{trend}", f"重心 {cent} Hz {_brightness(cent)}" if cent else "重心 なし(ほぼ無音)"]
    if d.get("tempo"):
        parts.append(f"拍 およそ {d['tempo']}")
    if run:
        parts.append(f"いま {run} 秒 静か")
    elif quiet:
        parts.append(f"途中に静けさ {quiet} 秒")
    return "、".join(parts)


def now_text(base: Path | None = None, now: datetime | None = None, character_id: str | None = None) -> str:
    s = session(base)
    if not s:
        return ""
    d = _load_json(music_dir(base) / f"{s['id']}.json") or {"frames": []}
    pos = position(s, now)
    head = f"いま {_mmss(pos)}" if pos is not None else "いま ?"
    state = "(終わった)" if s.get("ended_at") else ""
    src = {"pc": "PC の中の音", "phone": "ありさんのスマホが聞いた音", "mic": "体のマイク"}.get(s.get("source"), s.get("source", ""))
    tail = ""
    if s.get("ended_at") and s.get("title"):
        tail = f"。答え合わせ: {s['title']}" + (f"。ありさん「{s['note']}」" if s.get("note") else "")
    mine = ""
    if character_id:
        own = feels(s["id"], base).get(character_id) or []
        if own:
            mine = "。あなたがこれまでに書いたこと: " + " / ".join(f"[{_mmss(int(f.get('t') or 0))}] {f['text']}" for f in own[-3:])
    return f"聴いている回{state}: {head}({src})。{describe(d, pos)}{tail}{mine}"


# ---- 感想(封をして書く)と、まわりの記録 ----

def feel_path(sid: str, base: Path | None = None) -> Path:
    return music_dir(base) / f"{sid}.feel.json"


def feels(sid: str | None = None, base: Path | None = None) -> dict[str, list[dict]]:
    sid = sid or (session(base) or {}).get("id")
    if not sid:
        return {}
    d = _load_json(feel_path(sid, base)) or {}
    return {k: v for k, v in d.items() if isinstance(v, list)}


def feel(character_id: str, text: str, base: Path | None = None, now: datetime | None = None) -> dict:
    """その子の感想を 1 件足す(封。画面は 3 人そろってから開ける)。回が無ければ ValueError"""
    s = session(base)
    if not s:
        raise ValueError("聴いている回が無い")
    text = " ".join(text.split())[:600]
    if not text:
        raise ValueError("中身が空")
    now = now or datetime.now()
    d = _load_json(feel_path(s["id"], base)) or {}
    lst = d.setdefault(character_id, [])
    lst.append({"t": position(s, now), "at": now.replace(microsecond=0).isoformat(), "text": text})
    _save_json(feel_path(s["id"], base), d)
    return {"id": s["id"], "count": len(lst), "t": lst[-1]["t"]}


def wrote(sid: str | None, character_ids: list[str], base: Path | None = None) -> dict:
    """だれが何件書いたか と、全員書いたか"""
    f = feels(sid, base)
    counts = {c: len(f.get(c) or []) for c in character_ids}
    return {"counts": counts, "all": bool(character_ids) and all(counts.values())}


def around(sid: str | None = None, base: Path | None = None, now: datetime | None = None) -> str:
    """その回のあいだの部屋の記録(scripts/room_log.py の 10 分ごと)と気配。無ければ空"""
    s = session(base) if not sid or (session(base) or {}).get("id") == sid else _load_json(session_path(base))
    if not s:
        return ""
    try:
        t0 = datetime.fromisoformat(s["started_at"])
        t1 = datetime.fromisoformat(s["ended_at"]) if s.get("ended_at") else (now or datetime.now())
    except (KeyError, TypeError, ValueError):
        return ""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    parts = []
    try:
        import room_log
        rows = []
        for day in sorted({t0.strftime("%Y%m%d"), t1.strftime("%Y%m%d")}):
            rows += [r for r in room_log.day_rows(base, day) if t0.isoformat() <= r.get("ts", "") <= t1.isoformat()]
        noise = [dev["noise"] for r in rows for dev in r.get("devices", {}).values() if isinstance(dev.get("noise"), (int, float))]
        co2 = [dev["eco2"] for r in rows for dev in r.get("devices", {}).values() if isinstance(dev.get("eco2"), (int, float))]
        moves = sum(1 for r in rows for dev in r.get("devices", {}).values() if dev.get("move"))
        if noise:
            parts.append(f"部屋の音 {min(noise):.0f}〜{max(noise):.0f} dB")
        if co2:
            parts.append(f"CO2 {min(co2)}〜{max(co2)} ppm")
        if rows:
            parts.append(f"机の動き {moves} 回/{len(rows)} 読み")
    except Exception:
        pass
    try:
        import presence_watch
        ev = []
        for day in sorted({t0.strftime("%Y%m%d"), t1.strftime("%Y%m%d")}):
            p = presence_watch.events_path(base or data_dir(), datetime.strptime(day, "%Y%m%d"))
            if p.exists():
                ev += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        ev = [e for e in ev if t0.isoformat() <= e.get("ts", "") <= t1.isoformat()]
        if ev:
            parts.append("気配: " + "、".join(f"{e['ts'][11:16]} {e.get('place', '')}に{'近づいた' if e.get('type') == 'arrived' else '離れた'}" for e in ev[:6]))
    except Exception:
        pass
    return "聴いているあいだの部屋: " + "、".join(parts) if parts else ""


def note_text(sid: str | None, names: dict[str, str], base: Path | None = None) -> str:
    """3 人の感想と答え合わせを 1 つの文に(交換ノートへ)"""
    s = session(base)
    if not s:
        return ""
    sid = sid or s["id"]
    f = feels(sid, base)
    out = [f"🎧 いっしょに聴いた({s['started_at'][:10].replace('-', '/')} {s['started_at'][11:16]})" + (f" — {s['title']}" if s.get("title") else "")]
    if s.get("note"):
        out.append(f"ありさん「{s['note']}」")
    w = wave(sid, base)
    if w:
        out.append(w)
    for cid, lst in f.items():
        for x in lst:
            out.append(f"{names.get(cid, cid)} [{_mmss(int(x.get('t') or 0))}] {x['text']}")
    ar = around(sid, base)
    if ar:
        out.append(ar)
    return "\n".join(out)


def line(base: Path | None = None, now: datetime | None = None) -> str:
    """見に行けるものの 1 行。回が無い・終わって 3 時間より古ければ何も出さない"""
    s = session(base)
    if not s:
        return ""
    now = now or datetime.now()
    if s.get("ended_at"):
        try:
            if (now - datetime.fromisoformat(s["ended_at"])).total_seconds() > 3 * 3600:
                return ""
        except ValueError:
            return ""
    return now_text(base, now)


def wave(sid: str | None = None, base: Path | None = None, width: int = 60) -> str:
    s = session(base)
    sid = sid or (s or {}).get("id")
    d = _load_json(music_dir(base) / f"{sid}.json") if sid else None
    if not d or not d.get("frames"):
        return ""
    bars = "▁▂▃▄▅▆▇█"
    fr = d["frames"]
    step = max(1, math.ceil(len(fr) / width))
    out = []
    for i in range(0, len(fr), step):
        chunk = fr[i:i + step]
        lv = sum(f["level"] for f in chunk) / len(chunk)
        out.append(bars[min(7, int(lv * 8))])
    return f"{_mmss(0)} {''.join(out)} {_mmss(d.get('seconds', len(fr)))}" + (f"  拍 {d['tempo']}" if d.get("tempo") else "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start"); p.add_argument("--source", default="pc", choices=["pc", "phone", "mic"]); p.add_argument("--by", default="arisan")
    p = sub.add_parser("stop"); p.add_argument("--title", default=None); p.add_argument("--note", default=None)
    p = sub.add_parser("listen"); p.add_argument("--source", default="pc", choices=["pc"]); p.add_argument("--seconds", type=int, default=300); p.add_argument("--device", default=None)
    p = sub.add_parser("analyze"); p.add_argument("file"); p.add_argument("--id", default=None)
    p = sub.add_parser("now"); p.add_argument("--character", default=None)
    sub.add_parser("line")
    p = sub.add_parser("wave"); p.add_argument("id", nargs="?", default=None)
    p = sub.add_parser("feel"); p.add_argument("character_id"); p.add_argument("text")
    p = sub.add_parser("around"); p.add_argument("id", nargs="?", default=None)
    p = sub.add_parser("note"); p.add_argument("id", nargs="?", default=None)
    a = ap.parse_args()
    if a.cmd == "start":
        s = start(a.source, a.by)
        print(f"始めた: {s['id']}({s['source']}、{s['started_at'][11:16]})")
    elif a.cmd == "stop":
        s = stop(a.title, a.note)
        print("終えた" if s else "回が無い")
    elif a.cmd == "listen":
        return listen_pc(a.seconds, device=a.device)
    elif a.cmd == "analyze":
        x = decode_file(a.file)
        d = analyze_samples(x)
        sid = a.id or ("file_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        _save_json(music_dir() / f"{sid}.json", {"id": sid, "source": "file", "path": str(a.file), **d})
        print(f"{sid}: {d['seconds']} 秒、拍 {d['tempo']}")
        print(wave(sid))
    elif a.cmd == "now":
        print(now_text(character_id=a.character))
    elif a.cmd == "line":
        t = line()
        if t:
            print(t)
    elif a.cmd == "feel":
        try:
            r = feel(a.character_id, a.text)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"封をして書いた({_mmss(int(r['t'] or 0))} のところ。{r['count']} 件目)。3 人そろったら並びます")
    elif a.cmd == "around":
        print(around(a.id))
    elif a.cmd == "note":
        print(note_text(a.id, {}))
    else:
        print(wave(a.id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
