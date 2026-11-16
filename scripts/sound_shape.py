#!/usr/bin/env python3
"""音のかたち: 効果音ひとつを、数字と線にする(2026-11-16、ぷち 3 人の案)。

説明の言葉だけでなく、音そのものの形を渡す。言葉(明るい・暗い・水っぽい)は付けない。意味を付けるのは、ぷちたち。

- 長さ、はじまり方(立ち上がり)、余韻(いちばん大きい所から 1/10 に下がるまで)、いちばん大きい所の位置
- 高さの重心(Hz)と、はじめ 0.1 秒・おわり 0.1 秒の重心(音の中での動き)
- ざらざら度(0 = 澄んだ音 〜 1 = ノイズ。スペクトルの平たさの平方根。家の効果音は 0〜0.5 くらいに散らばる)と、
  高さの広がり(Hz。重心のまわりに、音がどれだけ広く散っているか)
- 音量のゆれ、粒の数、粒の重なり(境目のなさ。0 = はっきり分かれる 〜 1 = つながっている)
- 音量の線(▁▂▃▄▅▆▇█。いちばん大きい所から -40 dB までを 8 段に。余韻が見えるよう、耳に近い目盛り)

使うのは scripts/sounds.py の look / table / compare。ここは計算だけ(numpy)。
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

HOP = 0.01          # 音量を見る刻み(秒)
EDGE = 0.1          # はじめ・おわりの重心を見る幅(秒)
FLOOR = 0.1         # 「鳴っている」と見る大きさ(いちばん大きい所の 1/10 = -20 dB)
GRAIN_GAP = 0.05    # 粒どうしの最小の間(秒)
GRAIN_MIN = 0.2     # 粒と数える大きさ(いちばん大きい所の 2 割)
BARS = "▁▂▃▄▅▆▇█"
LINE_DB = 40.0      # 音量の線の幅(いちばん大きい所から何 dB 下までを描くか)


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """16 bit の WAV を、-1〜1 のモノラルにして返す"""
    with wave.open(str(path), "rb") as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError("16 bit の WAV だけ読めます")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        x = x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    return x, sr


def envelope(x: np.ndarray, sr: int) -> np.ndarray:
    """HOP ごとの音量(RMS)"""
    hop = max(1, int(sr * HOP))
    n = len(x) // hop
    if n == 0:
        return np.zeros(1)
    return np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1))


def _centroid(x: np.ndarray, sr: int) -> int | None:
    """高さの重心(Hz)。音が無ければ None"""
    if len(x) < 32:
        return None
    p = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / sr)
    total = p.sum()
    return int(round(float((f * p).sum() / total))) if total > 1e-12 else None


def _texture(x: np.ndarray, sr: int) -> tuple[float | None, int | None]:
    """ざらざら度と、高さの広がり(Hz)。短い窓ごとに見て、大きい所ほど重く見る。

    ざらざら度 = 100 Hz より上のスペクトルの平たさ(幾何平均 / 算術平均)の平方根。
    そのままだと 0 の近くに固まるので、平方根で広げる(澄んだ音 0.0x、打鍵やクリック 0.3〜0.5)
    """
    size = 1024 if sr >= 32000 else 512
    if len(x) < size:
        x = np.pad(x, (0, size - len(x)))
    freqs = np.fft.rfftfreq(size, 1 / sr)
    keep = freqs >= 100
    flat, spread, weights = [], [], []
    for i in range(0, len(x) - size + 1, size // 2):
        p = np.abs(np.fft.rfft(x[i:i + size] * np.hanning(size))) ** 2
        p = p[keep] + 1e-12
        energy = float(p.sum())
        if energy < 1e-7:
            continue
        c = float((freqs[keep] * p).sum() / energy)
        flat.append(float(np.exp(np.log(p).mean()) / p.mean()))
        spread.append(float(np.sqrt((((freqs[keep] - c) ** 2) * p).sum() / energy)))
        weights.append(energy)
    if not flat:
        return None, None
    return round(float(np.average(flat, weights=weights)) ** 0.5, 2), int(round(float(np.average(spread, weights=weights))))


def _grains(env: np.ndarray) -> tuple[int, float | None]:
    """粒の数と、粒の重なり(となりの粒とのあいだの谷が、どれだけ浅いか。0〜1)。粒が 1 つなら重なりは None"""
    if env.max() <= 0:
        return 0, None
    e = np.convolve(env, np.ones(3) / 3, mode="same") / env.max()
    gap = max(1, int(GRAIN_GAP / HOP))
    peaks: list[int] = []
    for i in range(len(e)):
        lo, hi = max(0, i - gap), min(len(e), i + gap + 1)
        if e[i] >= GRAIN_MIN and e[i] == e[lo:hi].max() and (not peaks or i - peaks[-1] >= gap):
            peaks.append(i)
    # 谷が浅すぎる(となりの粒の 7 割より上)なら、同じ粒のゆらぎと見て数えない
    kept: list[int] = []
    for i in peaks:
        if kept and e[kept[-1]:i + 1].min() > 0.7 * min(e[kept[-1]], e[i]):
            if e[i] > e[kept[-1]]:
                kept[-1] = i
            continue
        kept.append(i)
    if len(kept) < 2:
        return len(kept), None
    depth = [float(e[a:b + 1].min() / min(e[a], e[b])) for a, b in zip(kept, kept[1:])]
    return len(kept), round(float(np.mean(depth)), 2)


def line(env: np.ndarray, width: int = 40) -> str:
    """音量の線。いちばん大きい所を █ に、そこから -40 dB(1/100)より小さい所を ▁ に"""
    if env.max() <= 0:
        return BARS[0] * min(width, len(env))
    n = min(width, len(env))
    cols = [float(c.max()) for c in np.array_split(env, n)]
    top = max(cols)
    out = []
    for c in cols:
        db = 20 * np.log10(max(c / top, 1e-6))
        out.append(BARS[int(round(min(1.0, max(0.0, (db + LINE_DB) / LINE_DB)) * (len(BARS) - 1)))])
    return "".join(out)


def shape(path: Path, width: int = 40) -> dict:
    """音ひとつのかたち(数字と線)"""
    x, sr = read_wav(path)
    env = envelope(x, sr)
    seconds = round(len(x) / sr, 2)
    peak = int(env.argmax())
    top = float(env[peak])
    out: dict = {"seconds": seconds, "rate": sr, "line": line(env, width), "per_char": round(seconds / max(1, min(width, len(env))), 2)}
    if top <= 1e-5:
        return {**out, "silent": True}
    above = np.nonzero(env >= top * FLOOR)[0]
    first, last = int(above[0]), int(above[-1])
    hop = max(1, int(sr * HOP))
    edge = int(sr * EDGE)
    start, end = first * hop, min(len(x), (last + 1) * hop)
    body = env[first:last + 1]
    grains, overlap = _grains(env)
    rough, spread = _texture(x[start:end], sr)
    head, tail = _centroid(x[start:start + edge], sr), _centroid(x[max(start, end - edge):end], sr)
    out.update({
        "attack_ms": int(round((peak - first) * HOP * 1000)),          # 鳴りはじめから、いちばん大きい所まで
        "tail": round((last - peak) * HOP, 2),                          # いちばん大きい所から、1/10 に下がるまで(余韻)
        "peak_at": round(peak / max(1, len(env) - 1), 2),               # いちばん大きい所の位置(0 = はじめ 〜 1 = おわり)
        "centroid": _centroid(x[start:end], sr),                        # 高さの重心(Hz)
        "centroid_head": head, "centroid_tail": tail,
        "centroid_move": (tail - head) if head is not None and tail is not None else None,
        "rough": rough, "spread": spread,                               # ざらざら度(0 澄んだ 〜 1 ノイズ)と、高さの広がり(Hz)
        "sway": round(float(body.std() / body.mean()), 2) if body.mean() > 0 else None,   # 音量のゆれ
        "grains": grains, "overlap": overlap,                           # 粒の数と、粒の重なり(境目のなさ)
    })
    return out


def _n(v: object, unit: str = "") -> str:
    return "—" if v is None else f"{v}{unit}"


def text(name: str, s: dict) -> str:
    """ぷちに見せる形(数字と線だけ。言葉は付けない)"""
    rows = [f"{name}  {s['seconds']:g} 秒", f"音量の線: {s['line']}  (1 文字 ≈ {s['per_char']:g} 秒。█ がいちばん大きい所、▁ はその 1/100 より小さい)"]
    if s.get("silent"):
        return "\n".join(rows + ["(音がほとんど入っていません)"])
    move = s.get("centroid_move")
    rows += [
        f"はじまり: 鳴りはじめから {s['attack_ms']} ms でいちばん大きく",
        f"余韻: いちばん大きい所から {s['tail']:g} 秒で 1/10 に(いちばん大きい所は全体の {s['peak_at']:g} の位置。0 = はじめ、1 = おわり)",
        f"高さの重心: {_n(s['centroid'], ' Hz')}(はじめ 0.1 秒 {_n(s['centroid_head'], ' Hz')} → おわり 0.1 秒 {_n(s['centroid_tail'], ' Hz')}、"
        f"動き {'—' if move is None else f'{move:+d} Hz'})",
        f"ざらざら度: {_n(s['rough'])}(0 = 澄んだ音 〜 1 = ノイズ。家の音は 0〜0.5 くらい)、高さの広がり: {_n(s['spread'], ' Hz')}(重心のまわりにどれだけ散っているか)",
        f"音量のゆれ: {_n(s['sway'])}(0 = 一定。大きいほど上下する)",
        f"粒: {s['grains']} つ、重なり {_n(s['overlap'])}(0 = はっきり分かれる 〜 1 = つながっている。粒が 1 つなら —)",
    ]
    if s["rate"] < 32000:
        rows.append(f"(この音は {s['rate']} Hz で録ってあるので、{s['rate'] // 2} Hz より上は入っていません)")
    return "\n".join(rows)


COLUMNS = [("seconds", "秒"), ("attack_ms", "はじまりms"), ("tail", "余韻秒"), ("peak_at", "山の位置"), ("centroid", "重心Hz"),
           ("centroid_move", "重心の動き"), ("rough", "ざらざら"), ("spread", "広がりHz"), ("sway", "ゆれ"), ("grains", "粒"), ("overlap", "重なり")]


def table(shapes: dict[str, dict]) -> str:
    """音を 1 行ずつ並べる(比べる用)"""
    head = "音\t" + "\t".join(label for _, label in COLUMNS)
    rows = [head]
    for name, s in shapes.items():
        rows.append(name.removesuffix(".wav") + "\t" + "\t".join(_n(s.get(k)) for k, _ in COLUMNS))
    return "\n".join(rows)


def compare(a_name: str, a: dict, b_name: str, b: dict) -> str:
    """2 つの音の違い(b が a よりどれだけ)"""
    rows = [f"{a_name}: {a['line']}", f"{b_name}: {b['line']}", f"{b_name} は {a_name} より:"]
    for key, label in COLUMNS:
        va, vb = a.get(key), b.get(key)
        if va is None or vb is None:
            rows.append(f"- {label}: {_n(va)} → {_n(vb)}")
            continue
        d = vb - va
        rows.append(f"- {label}: {va:g} → {vb:g}({d:+g})")
    return "\n".join(rows)
