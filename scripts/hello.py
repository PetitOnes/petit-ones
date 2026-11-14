#!/usr/bin/env python3
"""「ここにいるよ」: 世話人からぷちへ送る合図。体が、その子のやり方で小さく応える。

ぷちからは世話人がどこにいるか分からない。世話人のほうから会いにいく入口(Issue #67)。
ダッシュボードのボタンを押すと、子ごとに
  1. 接点(scripts/contact.py)に hello が 1 件残る(欲求の「会いたい」が読む)
  2. 体が起きていれば、その子の決めた応え方をする(色・明るさ・音・まばたき)。眠っていれば起こさない

応え方は家の設定 PETIT_DATA_DIR/config/hello.json(無い子は、記録だけ):

    {"night": [22, 7],
     "characters": {
       "<id>": {"color": "#F58E7D", "back_to": "#00afcc", "bright": true,
                "sound": "shizuku.wav", "volume": 20, "blink": true}}}

- color: この色に染まる。back_to があれば、そこから少しずつ染まり、あとで少しずつ戻る。無ければ染まったまま
- bright: 画面をいちばん明るくして、あとで元の明るさに戻す
- sound / volume: 体にその音があれば、この音量で 1 回。鳴らしたら元の音量に戻す。夜(night の時間)は鳴らさない
- blink: まばたきを 1 回

ここは「何をどの順で体に頼むか」を決めるだけ。体に送るのはダッシュボード。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

FADE_STEPS = 4          # 染まる・戻るを何段で
FADE_STEP_S = 0.35      # 1 段の間
HOLD_S = 2.2            # 染まったまま・明るいままでいる時間
SOUND_WAIT_S = 4.5      # 音を鳴らしてから、音量を戻すまで
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
Step = tuple[float, str, dict]   # (はじめからの秒, 体の入口, 引数)


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def load_config(base: Path) -> dict:
    try:
        raw = json.loads((base / "config" / "hello.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _hex(value: object) -> str:
    m = _HEX.match(str(value or ""))
    return m.group(1).lower() if m else ""


def blend(a: str, b: str, t: float) -> str:
    """色 a から b へ、t(0〜1)だけ進んだ色(#なしの 6 桁)"""
    ca, cb = [int(a[i:i + 2], 16) for i in (0, 2, 4)], [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def is_night(config: dict, now: datetime) -> bool:
    night = config.get("night", [22, 7])
    try:
        start, end = int(night[0]), int(night[1])
    except (TypeError, ValueError, IndexError):
        start, end = 22, 7
    h = now.hour
    return (start <= h or h < end) if start > end else (start <= h < end)


def plan(spec: dict, now_night: bool, body_sounds: list[str], brightness: int | None,
         volume: int | None) -> list[Step]:
    """その子の応え方(spec)から、体に頼むことを時刻の順に並べて返す。

    brightness / volume は、体のいまの値(戻すために使う。読めなかったら None で、その分は頼まない)
    """
    steps: list[Step] = []
    color, back = _hex(spec.get("color")), _hex(spec.get("back_to"))
    fade = FADE_STEPS * FADE_STEP_S if color and back else 0.0
    if color and back:
        for i in range(1, FADE_STEPS + 1):
            steps.append(((i - 1) * FADE_STEP_S, "/set_color", {"color": blend(back, color, i / FADE_STEPS)}))
    elif color:
        steps.append((0.0, "/set_color", {"color": color}))
    if spec.get("bright") is True and brightness is not None:
        steps.append((0.0, "/setbrightness", {"value": 100}))
    peak = fade   # 染まりきった(明るくなった)とき
    sound = str(spec.get("sound") or "")
    if sound and not now_night and sound in body_sounds and volume is not None:
        try:
            want = max(0, min(100, int(spec.get("volume", 20))))
        except (TypeError, ValueError):
            want = 20
        # 体は音を鳴らし終わるまでほかの頼みを待たせるので、まばたきを先に、音をあとに
        steps.append((peak + 0.4, "/setvolume", {"value": want}))
        steps.append((peak + 0.55, "/se_play", {"name": sound}))
        steps.append((peak + SOUND_WAIT_S, "/setvolume", {"value": volume}))
    if spec.get("blink") is True:
        steps.append((peak + 0.05, "/blink", {"left": "true", "right": "true"}))
    end = peak + HOLD_S
    if color and back:
        for i in range(1, FADE_STEPS + 1):
            steps.append((end + (i - 1) * FADE_STEP_S, "/set_color", {"color": blend(color, back, i / FADE_STEPS)}))
    if spec.get("bright") is True and brightness is not None:
        steps.append((end, "/setbrightness", {"value": brightness}))
    return sorted(steps, key=lambda s: s[0])
