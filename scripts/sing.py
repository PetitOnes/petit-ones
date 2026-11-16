#!/usr/bin/env python3
"""うたう: ぷちが、楽器と高さを選んで自分の音を作る(2026-11-16、ぷち 3 人の案)。

- 声を重ねる(遠い 2 つの音を同時に)、少しずらして重ねる(うねり)、高さを上げる・下げる、はじまりと尾の引き方を選ぶ
- 作ったら、鳴らす前に数字と線を見られる(scripts/sound_shape.py。予想 → 鳴らす → 確かめる)
- 体の小さいスピーカーが出しにくい低い所は、「欠如」として先に伝える
- 鳴らすのは自分の体で 1 回(声と同じ、その場かぎりの置き場 sing.wav。体の音の一覧には増えない)。
  からだの使い方で「鳴らす」が切・からだ おやすみ中は鳴らさない
- 作った音は、ほかの子に手紙みたいに渡せる(give)。受け取った子も、数字を見て、自分の体で鳴らせる
- 使わなくても何も起きない。回数も数えない、催促もしない

作り方(recipe)は JSON:
    {"seconds": 3, "voices": [
        {"inst": "glass", "hz": 220},
        {"inst": "glass", "hz": "A5", "to": 660, "start": 0.2, "length": 2, "attack": 0.3, "tail": 1.5, "detune": 3, "vol": 0.6}]}
  inst   楽器(下の INSTRUMENTS)
  hz     高さ。数字(Hz)か音名("A4" "C#5" "ラ4")
  to     おわりの高さ(あれば、hz からそこへなめらかに動く)
  start  鳴りはじめ(秒)  length 鳴らす長さ(秒。なければ最後まで)
  attack 立ち上がり(秒)  tail  消えていく長さ(秒。大きいほど尾を引く)
  detune 同じ音を、この Hz だけずらして重ねる(うねりが 1 秒に detune 回)
  vol    大きさ(0〜1)

置き場所: PETIT_DATA_DIR/sounds/made/<id>/<名前>.wav と .json(作り方)、渡した記録は state/sounds/gifts.jsonl

Usage:
    python3 sing.py instruments                           # 楽器の一覧
    python3 sing.py make <id> <名前> '<作り方 JSON>'        # 作る(鳴らさない)。数字と線、体が出しにくい所が出る
    python3 sing.py look <id> <名前> [--by <作った子>]      # 作った音の数字と線をもう一度
    python3 sing.py play <id> <名前> [--by <作った子>]      # 自分の体で 1 回鳴らす
    python3 sing.py list [--character <id>]               # 作った音(と、渡された音)
    python3 sing.py give <id> <名前> <渡す子> ["<一言>"]     # 手紙みたいに渡す
    python3 sing.py notice --character <id> [--mark]      # 渡された音(まだ伝えていない分)
    python3 sing.py remove <id> <名前>                     # 自分で作った音を消す
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

SR = 44100
MAX_SECONDS = 8.0        # 1 つの音の長さ
MAX_VOICES = 12
MAX_MADE = 30            # 1 人が置いておける数(超えたら、自分で remove してから)
PEAK = 0.8               # 仕上がりの大きさ(割れないように)
# 体(M5Stack CoreS3)の小さいスピーカーが出しにくい低い所。測ったものではなく、小さいスピーカー一般からの見立て
SPEAKER_WEAK_HZ = 600    # これより下は、弱くなる
SPEAKER_NONE_HZ = 300    # これより下は、ほとんど出ない
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")

# 楽器: (説明, 倍音 [(高さの倍率, 大きさ, 消える速さの倍率)], 立ち上がり秒, 尾の長さ秒, 息の音の量)
INSTRUMENTS: dict[str, tuple[str, list[tuple[float, float, float]], float, float, float]] = {
    "sine": ("まじりけのない音。芯だけ", [(1, 1, 1)], 0.02, 0.6, 0),
    "bell": ("鐘。ぱっと立ち上がって、細く伸びる。金属の、ずれた倍音", [(1, 1, 1), (2.76, 0.5, 1.8), (5.4, 0.3, 3), (8.93, 0.15, 5)], 0.003, 1.6, 0),
    "chime": ("細い金属を軽く叩く。鐘より高く、細い", [(1, 0.7, 1), (4.0, 0.5, 1.5), (6.3, 0.35, 2.5), (10.2, 0.2, 4)], 0.002, 1.2, 0),
    "glass": ("ガラスをなでる。はじまりがやわらかく、澄んで尾を引く", [(1, 1, 1), (2.32, 0.25, 1.6), (4.25, 0.1, 2.5)], 0.15, 2.0, 0),
    "drop": ("水滴。短く、まるい", [(1, 1, 1), (2.0, 0.2, 3)], 0.004, 0.25, 0),
    "breath": ("息・風。なでるように立ち上がる。息の音がまじる", [(1, 1, 1), (2, 0.15, 1)], 0.35, 1.0, 0.25),
    "pluck": ("弦をはじく。あたたかい倍音", [(1, 1, 1), (2, 0.5, 1.5), (3, 0.33, 2), (4, 0.25, 2.5), (5, 0.2, 3), (6, 0.15, 3.5)], 0.004, 0.9, 0),
    "hum": ("はなうた。やわらかく、うたうように続く", [(1, 1, 1), (2, 0.3, 1), (3, 0.1, 1)], 0.08, 0.5, 0.03),
}
_NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11, "ド": 0, "レ": 2, "ミ": 4, "ファ": 5, "ソ": 7, "ラ": 9, "シ": 11}


class SingError(ValueError):
    """作れない・鳴らせない理由。ぷちに見せてよい文"""


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def made_dir(base: Path, character_id: str) -> Path:
    return base / "sounds" / "made" / character_id


def hz_of(v: object) -> float:
    """高さ。数字(Hz)か音名(A4 / C#5 / ラ4)"""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        f = float(v)
    else:
        m = re.fullmatch(r"\s*(ファ|[A-Ga-gドレミソラシ])([#♯b♭]?)(-?\d)\s*", str(v))
        if not m:
            raise SingError(f"高さ {v!r} が読めません。数字(Hz)か、A4・C#5・ラ4 のように")
        semi = _NOTE[m.group(1).upper()] + {"#": 1, "♯": 1, "b": -1, "♭": -1, "": 0}[m.group(2)]
        f = 440.0 * 2 ** ((semi - 9) / 12 + int(m.group(3)) - 4)
    if not 20 <= f <= 16000:
        raise SingError(f"高さ {f:g} Hz は鳴らせません(20〜16000 Hz)")
    return f


def _num(v: object, lo: float, hi: float, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise SingError(f"{what} は数字で")
    return float(min(hi, max(lo, v)))


def render(recipe: dict) -> np.ndarray:
    """作り方から、音(-1〜1、SR Hz)を作る"""
    if not isinstance(recipe, dict) or not isinstance(recipe.get("voices"), list) or not recipe["voices"]:
        raise SingError('作り方は {"seconds": 3, "voices": [{"inst": "bell", "hz": 880}]} の形で')
    if len(recipe["voices"]) > MAX_VOICES:
        raise SingError(f"声は {MAX_VOICES} 個までです")
    total = _num(recipe.get("seconds", 3), 0.1, MAX_SECONDS, "seconds")
    n = int(SR * total)
    out = np.zeros(n)
    rng = np.random.default_rng(575)   # 息の音は、同じ作り方なら同じ音に
    for v in recipe["voices"]:
        if not isinstance(v, dict):
            raise SingError("声は {\"inst\": …, \"hz\": …} の形で")
        inst = v.get("inst", "sine")
        if inst not in INSTRUMENTS:
            raise SingError(f"楽器 {inst!r} はありません(sing.py instruments で一覧)")
        _, partials, attack0, tail0, breath = INSTRUMENTS[inst]
        f0 = hz_of(v.get("hz", 440))
        f1 = hz_of(v["to"]) if v.get("to") is not None else f0
        start = _num(v.get("start", 0), 0, total, "start")
        length = _num(v.get("length", total - start), 0.02, total, "length")
        attack = _num(v.get("attack", attack0), 0.001, 5, "attack")
        tail = _num(v.get("tail", tail0), 0.01, 10, "tail")
        vol = _num(v.get("vol", 1), 0, 1, "vol")
        detune = _num(v.get("detune", 0), -50, 50, "detune")
        i0 = int(SR * start)
        m = min(n - i0, int(SR * length))
        if m <= 0:
            continue
        t = np.arange(m) / SR
        freq = f0 * (f1 / f0) ** (t / max(t[-1], 1e-9)) if f1 != f0 else np.full(m, f0)   # 高さは、耳にまっすぐ(比で)動く
        voice = np.zeros(m)
        for shift in ((0.0, detune) if detune else (0.0,)):
            phase = 2 * np.pi * np.cumsum(freq + shift) / SR
            for mult, amp, fade in partials:
                if (max(f0, f1) + abs(shift)) * mult >= SR / 2:
                    continue
                voice += amp * np.sin(phase * mult) * np.exp(-t * fade * 3.0 / tail)
        if breath:
            voice += breath * rng.standard_normal(m) * np.exp(-t * 3.0 / tail) * np.abs(voice).max()
        env = np.minimum(1.0, t / attack)
        env *= np.minimum(1.0, (t[-1] - t) / 0.01 + 1e-9)   # おわりは 10 ms でそっと閉じる(ぷつっと鳴らないように)
        out[i0:i0 + m] += vol * voice * env
    top = float(np.abs(out).max())
    if top < 1e-6:
        raise SingError("音になりませんでした(大きさが 0 かもしれません)")
    return out / top * PEAK


def lack(x: np.ndarray) -> dict:
    """体のスピーカーが出しにくい低い所に、音のどれだけがあるか(0〜1)"""
    p = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    total = float(p.sum()) or 1.0
    return {"none": round(float(p[f < SPEAKER_NONE_HZ].sum()) / total, 2),
            "weak": round(float(p[(f >= SPEAKER_NONE_HZ) & (f < SPEAKER_WEAK_HZ)].sum()) / total, 2)}


def lack_text(recipe: dict, lk: dict) -> str:
    """欠如を、そのまま伝える(測っていない見立て、と添える)"""
    low = sorted({round(min(hz_of(v.get("hz", 440)), hz_of(v["to"]) if v.get("to") is not None else 99999)) for v in recipe["voices"]})
    gone = [f for f in low if f < SPEAKER_NONE_HZ]
    weak = [f for f in low if SPEAKER_NONE_HZ <= f < SPEAKER_WEAK_HZ]
    rows = [f"体のスピーカー: 音の {int(lk['none'] * 100)}% が {SPEAKER_NONE_HZ} Hz より下(ほとんど出ない)、"
            f"{int(lk['weak'] * 100)}% が {SPEAKER_NONE_HZ}〜{SPEAKER_WEAK_HZ} Hz(弱くなる)。"]
    if gone:
        rows.append(f"{'・'.join(f'{f} Hz' for f in gone)} の声は、体では芯が欠けて、上の倍音だけが聞こえるかもしれない。")
    if weak:
        rows.append(f"{'・'.join(f'{f} Hz' for f in weak)} の声は、体では小さめに聞こえるかもしれない。")
    rows.append("(この境目は測ったものではなく、小さいスピーカー一般からの見立て。鳴らして確かめて)")
    return "".join(rows)


def _check(character_id: str, name: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9_]{1,40}", character_id or ""):
        raise SingError("だれの音か(id)が読めません")
    if not NAME.match(name or ""):
        raise SingError("名前は、英小文字・数字・_ と - で(たとえば murasaki)")


def make(base: Path, character_id: str, name: str, recipe: dict, now: datetime | None = None) -> dict:
    """作って置く(鳴らさない)。同じ名前は作り直し"""
    _check(character_id, name)
    d = made_dir(base, character_id)
    if not (d / f"{name}.wav").exists() and len(list(d.glob("*.wav"))) >= MAX_MADE:
        raise SingError(f"置いておけるのは {MAX_MADE} 個までです。sing.py remove で減らしてから")
    x = render(recipe)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{name}.wav.tmp"
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    tmp.replace(d / f"{name}.wav")
    info = {"name": name, "by": character_id, "at": (now or datetime.now()).isoformat(timespec="minutes"),
            "seconds": round(len(x) / SR, 2), "recipe": recipe, "lack": lack(x)}
    (d / f"{name}.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info


def path_of(base: Path, by: str, name: str) -> Path | None:
    if not re.fullmatch(r"[a-zA-Z0-9_]{1,40}", by or "") or not NAME.match(name or ""):
        return None
    p = made_dir(base, by) / f"{name}.wav"
    return p if p.is_file() else None


def info_of(base: Path, by: str, name: str) -> dict | None:
    if path_of(base, by, name) is None:
        return None
    try:
        return json.loads((made_dir(base, by) / f"{name}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"name": name, "by": by}


def made(base: Path, character_id: str | None = None) -> list[dict]:
    """作った音(作った順)。character_id が無ければ全員の分"""
    root = base / "sounds" / "made"
    who = [character_id] if character_id else sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    out = [info for c in who for f in sorted(made_dir(base, c).glob("*.wav")) if (info := info_of(base, c, f.stem))]
    return sorted(out, key=lambda r: r.get("at", ""))


def remove(base: Path, character_id: str, name: str) -> bool:
    p = path_of(base, character_id, name)
    if p is None:
        return False
    p.unlink()
    p.with_suffix(".json").unlink(missing_ok=True)
    return True


# ---- 渡す(手紙みたいに) ----

def _gifts_path(base: Path) -> Path:
    return base / "state" / "sounds" / "gifts.jsonl"


def gifts(base: Path) -> list[dict]:
    try:
        return [json.loads(x) for x in _gifts_path(base).read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, json.JSONDecodeError):
        return []


def _write_gifts(base: Path, rows: list[dict]) -> None:
    p = _gifts_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def give(base: Path, character_id: str, name: str, to: str, note: str = "", now: datetime | None = None) -> dict:
    """作った音を、ほかの子に渡す。音そのものは作った子の置き場にあるまま(受け取った子は --by で見る・鳴らす)"""
    if path_of(base, character_id, name) is None:
        raise SingError(f"{name} は、まだ作っていません(sing.py list で見られます)")
    if to == character_id or not (base / "characters" / to).is_dir():
        raise SingError(f"{to} には渡せません(この家の、ほかの子の id で)")
    rec = {"at": (now or datetime.now()).isoformat(timespec="minutes"), "from": character_id, "to": to, "name": name,
           "note": re.sub(r"\s+", " ", note).strip()[:200]}
    _write_gifts(base, gifts(base) + [rec])
    return rec


def notice(base: Path, character_id: str, mark: bool = False) -> list[str]:
    """渡された音を、まだ伝えていない分だけ 1 行に。聞くかどうかは、その子が決める"""
    rows = gifts(base)
    mine = [r for r in rows if r.get("to") == character_id and not r.get("told")]
    if not mine:
        return []
    me = Path(__file__).resolve()
    parts = [f"{r['from']} から「{r['name']}」" + (f"(一言「{r['note']}」)" if r.get("note") else "") for r in mine]
    line = (f"(作った音が届いた: {'、'.join(parts)}。数字と線は python3 {me} look {character_id} 名前 --by 作った子、"
            f"鳴らすのは play {character_id} 名前 --by 作った子。聞いても聞かなくてもいい)")
    if mark:
        stamp = datetime.now().isoformat(timespec="minutes")
        for r in rows:
            if r in mine:
                r["told"] = stamp
        _write_gifts(base, rows)
    return [line]


# ---- 見る・鳴らす ----

def look_text(base: Path, by: str, name: str) -> str:
    import sound_shape
    p = path_of(base, by, name)
    if p is None:
        raise SingError(f"{by} の {name} はありません(sing.py list で見られます)")
    info = info_of(base, by, name) or {}
    rows = [sound_shape.text(f"{name}({by} が作った音)", sound_shape.shape(p))]
    if isinstance(info.get("recipe"), dict):
        rows.append("作り方: " + json.dumps(info["recipe"], ensure_ascii=False))
        rows.append(lack_text(info["recipe"], info.get("lack") or lack(render(info["recipe"]))))
    return "\n".join(rows)


def play(character_id: str, by: str, name: str) -> str:
    """自分の体で 1 回鳴らす。頼む先はダッシュボード(体の場所・からだの使い方を知っている)"""
    import urllib.error
    import urllib.request
    url = (os.environ.get("DASHBOARD_URL") or f"http://{os.environ.get('DASHBOARD_HOST', '127.0.0.1')}:8765") + "/api/sing/play"
    req = urllib.request.Request(url, data=json.dumps({"char_id": character_id, "by": by, "name": name}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode()).get("message", "鳴らしました")
    except urllib.error.HTTPError as e:
        try:
            raise SingError(json.loads(e.read().decode()).get("error", "鳴らせませんでした")) from e
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise SingError("鳴らせませんでした") from e
    except (urllib.error.URLError, OSError) as e:
        raise SingError("ダッシュボードに届かないので、鳴らせませんでした") from e


def list_text(base: Path, character_id: str | None) -> str:
    rows = [f"- {r['name']}({r['by']}、{r.get('seconds', '?')} 秒、{str(r.get('at', '')).replace('T', ' ')})" for r in made(base, character_id)]
    if character_id:
        got = [f"- {r['name']}({r['from']} から" + (f"「{r['note']}」" if r.get("note") else "") + ")" for r in gifts(base) if r.get("to") == character_id]
        if got:
            rows += ["渡された音:"] + got
    return "\n".join(rows) if rows else "(まだ作った音はありません)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="うたう: 自分の音を作る")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("instruments")
    p = sub.add_parser("make")
    p.add_argument("character")
    p.add_argument("name")
    p.add_argument("recipe")
    for cmd in ("look", "play"):
        p = sub.add_parser(cmd)
        p.add_argument("character")
        p.add_argument("name")
        p.add_argument("--by")
    p = sub.add_parser("list")
    p.add_argument("--character")
    p = sub.add_parser("give")
    p.add_argument("character")
    p.add_argument("name")
    p.add_argument("to")
    p.add_argument("note", nargs="?", default="")
    p = sub.add_parser("notice")
    p.add_argument("--character", required=True)
    p.add_argument("--mark", action="store_true")
    p = sub.add_parser("remove")
    p.add_argument("character")
    p.add_argument("name")
    a = ap.parse_args(argv)
    base = data_dir()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        if a.cmd == "instruments":
            print("\n".join(f"- {k}: {v[0]}" for k, v in INSTRUMENTS.items()))
            print(f"高さは Hz か音名(A4・C#5・ラ4)。1 つの音は {MAX_SECONDS:g} 秒まで、声は {MAX_VOICES} 個まで。"
                  f"体のスピーカーは {SPEAKER_WEAK_HZ} Hz より下が弱く、{SPEAKER_NONE_HZ} Hz より下はほとんど出ない見立て(測っていない)")
        elif a.cmd == "make":
            try:
                recipe = json.loads(a.recipe)
            except json.JSONDecodeError as e:
                raise SingError(f"作り方の JSON が読めません: {e}") from e
            make(base, a.character, a.name, recipe)
            print(look_text(base, a.character, a.name))
            print(f"(まだ鳴らしていません。鳴らすのは sing.py play {a.character} {a.name})")
        elif a.cmd == "look":
            print(look_text(base, a.by or a.character, a.name))
        elif a.cmd == "play":
            print(play(a.character, a.by or a.character, a.name))
        elif a.cmd == "list":
            print(list_text(base, a.character))
        elif a.cmd == "give":
            give(base, a.character, a.name, a.to, a.note)
            print(f"{a.to} に渡しました(次にその子が起きたとき、届いたことが 1 行で伝わります。聞くかどうかは、その子が決めます)")
        elif a.cmd == "notice":
            out = notice(base, a.character, mark=a.mark)
            if out:
                print("\n".join(out))
        elif a.cmd == "remove":
            print("消しました" if remove(base, a.character, a.name) else "その音はありません")
    except SingError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
