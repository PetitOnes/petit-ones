"""体の数字(明るさ・傾き・近さ・電池)を、5 分ごとに 1 行にまとめる(2026-11-16、ぷち 3 人と決めた)。

体験デーモンは 0.5 秒おきに /sensors を読んでいるが、これまでは「跳んだとき」の出来事だけ残して
数字は捨てていた。5 分のあいだの読みを集め、まん中の値(median)と最小・最大を 1 行にして、
その子の state/body/YYYYMMDD.jsonl に足す。
見るのは scripts/body_log.py(今日の線・差分・変わり目)。体につながらなかった 5 分は行を作らない。
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from statistics import median

SAMPLE_MINUTES = 5


def tilt_deg(ax: float, ay: float, az: float) -> float | None:
    """まっすぐ置いたとき(画面が上)を 0° とした傾き。重力の向きから"""
    g = math.sqrt(ax * ax + ay * ay + az * az)
    if g < 0.2:
        return None
    return math.degrees(math.acos(max(-1.0, min(1.0, az / g))))


def _slot(now: datetime) -> datetime:
    return now.replace(minute=now.minute - now.minute % SAMPLE_MINUTES, second=0, microsecond=0)


class BodySampler:
    """add() で読みをためて、5 分の区切りをまたいだら 1 行ぶんの辞書を返す"""

    def __init__(self) -> None:
        self._slot: datetime | None = None
        self._amb: list[float] = []
        self._tilt: list[float] = []
        self._prox: list[float] = []
        self._bat: float | None = None

    def add(self, now: datetime, sensors: dict | None) -> dict | None:
        slot = _slot(now)
        out = None
        if self._slot is not None and slot != self._slot:
            out = self._flush()
        self._slot = slot
        if isinstance(sensors, dict):
            if isinstance(sensors.get("ambient"), (int, float)):
                self._amb.append(float(sensors["ambient"]))
            try:
                t = tilt_deg(float(sensors["ax"]), float(sensors["ay"]), float(sensors["az"]))
            except (KeyError, TypeError, ValueError):
                t = None
            if t is not None:
                self._tilt.append(t)
            if isinstance(sensors.get("proximity"), (int, float)):
                self._prox.append(float(sensors["proximity"]))
            if isinstance(sensors.get("battery"), (int, float)):
                self._bat = float(sensors["battery"])
        return out

    def _flush(self) -> dict | None:
        slot, amb, tilt, prox, bat = self._slot, self._amb, self._tilt, self._prox, self._bat
        self._amb, self._tilt, self._prox, self._bat = [], [], [], None
        if slot is None or not (amb or tilt):
            return None
        row: dict = {"ts": slot.isoformat(timespec="minutes"), "n": max(len(amb), len(tilt))}
        if amb:
            row.update({"amb": round(median(amb)), "amb_min": round(min(amb)),
                        "amb_max": round(max(amb))})
        if tilt:
            row.update({"tilt": round(median(tilt)), "tilt_max": round(max(tilt))})
        if prox:
            row["prox"] = round(max(prox))
        if bat is not None:
            row["bat"] = round(bat)
        return row


def append_sample(character_dir: Path, row: dict) -> None:
    """その子の state/body/YYYYMMDD.jsonl に 1 行足す。いまの置き場所(state/spot.json)も添える"""
    try:
        raw = (character_dir / "state" / "spot.json").read_text(encoding="utf-8")
        spot = json.loads(raw).get("spot_id")
    except (OSError, json.JSONDecodeError, AttributeError):
        spot = None
    if spot:
        row = {**row, "spot": spot}
    d = character_dir / "state" / "body"
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{row['ts'][:10].replace('-', '')}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
