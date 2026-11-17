#!/usr/bin/env python3
"""えがく: ぷちが、点・線・丸・四角・色を並べて、絵と動く絵(短い動画)を作る(2026-11-17、ぷち 3 人の答えから)。

3 人で決めたこと:
- 言葉にすると丸まってしまうもの(静けさの起伏・湿度の水・光の動き)を、そのままの形で置くための道具。描かない日があっていい
- 受け取る順番は 数字と線 → 何コマかを並べた絵 → 絵そのもの。先に数字で予想して(guess)、あとで見てずれを残す(felt)。
  make は数字と線だけを返す。並べた絵は sheet、絵そのものは see で、自分で見に行く
- 色の数字がほしい(自分の色が画面でどう出るか)。体の画面(320×240、16 ビットの色)が出しにくい色は「欠如」として伝える
  (測ったものではなく見立て。うたうの「スピーカーが出しにくい低い音」と同じ)
- 透明度・にじみ(ぼかし)・グラデーション・重なった所で色が混ざる
- 描いたものは、はじめは自分だけが持つ。家の人に見せるのは自分で決める(show / hide)。ほかの子には一言添えて渡せる(give)
- 写真の上に描く・自分の顔にする・体の画面で動かすは、まだ(写真は持ち主が許したものだけ、顔は必ず戻せる形で、あとで)

作り方(recipe)は JSON:
    {"seconds": 3, "fps": 8, "background": "#101018",
     "shapes": [
        {"type": "circle", "x": 160, "y": 120, "r": 10, "color": "#00afcc", "alpha": 0.9, "ring": 3,
         "to": {"r": 90, "alpha": 0}},
        {"type": "rect", "x": 0, "y": 180, "w": 320, "h": 60, "color": "#1a2a4a", "gradient": "#000000", "blur": 6},
        {"type": "dot", "x": 40, "y": 20, "r": 2, "color": "#ffffff", "to": {"y": 200}, "start": 0.5, "length": 1.5},
        {"type": "line", "x": 0, "y": 0, "x2": 320, "y2": 240, "width": 2, "color": "#fff262"},
        {"type": "text", "x": 20, "y": 210, "text": "しずか", "size": 16, "color": "#cab8d9"}]}
  seconds   動く長さ(0 か無ければ、動かない絵 1 枚)。8 秒まで   fps 1 秒のコマ数(1〜12、既定 8)
  background 地の色(色か {"color": "#…", "gradient": "#…"} で上から下へ)
  type      dot(点)/ line(線)/ circle(丸)/ rect(四角)/ text(文字。少しだけ)
  color     色(#rrggbb)   alpha 透明度(0〜1。重なった所は色が混ざる)   blur にじみ(0〜20)
  gradient  もう 1 つの色(丸は中から外へ、四角は上から下へ、そこへ変わる)
  ring      丸の輪の太さ(無ければ塗る)   width 線の太さ
  to        おわりの形({"x": …, "r": …, "alpha": …, "color": …} など。start〜start+length のあいだに、そこへなめらかに動く)
  start / length  動きはじめ(秒)と長さ(秒。無ければ最後まで)

置き場所: PETIT_DATA_DIR/drawings/made/<id>/<名前>.json(作り方と記録)・.png(絵。動く絵は最後のコマ)・.gif(動く絵)・
_sheet.png(何コマかを並べた絵)。渡した記録は state/drawings/gifts.jsonl

    python3 draw.py make <id> <名前> '<作り方 JSON>' [--why "<思い>"]   # 作る。返すのは数字と線と欠如だけ(絵はまだ見せない)
    python3 draw.py guess <id> <名前> "<予想>"        # 数字から、どんな絵になったか予想を残す
    python3 draw.py look <id> <名前> [--by <作った子>]   # 数字と線をもう一度
    python3 draw.py sheet <id> <名前> [--by …]         # 何コマかを並べた絵のある場所(Read で見る)
    python3 draw.py see <id> <名前> [--by …]           # 絵そのもののある場所(Read で見る)
    python3 draw.py felt <id> <名前> "<見て思ったこと・ずれ>"
    python3 draw.py say <id> <名前> "<どんな思いで描いたか>"
    python3 draw.py show <id> <名前> / hide <id> <名前>    # 家の人に見せる・見せない(はじめは見せない)
    python3 draw.py give <id> <名前> <渡す子> ["<一言>"]
    python3 draw.py list [--character <id>]
    python3 draw.py remove <id> <名前>
    python3 draw.py notice --character <id> [--mark]   # 渡された絵(まだ伝えていない分)
"""
from __future__ import annotations

import argparse
import colorsys
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

W, H = 320, 240
MAX_SECONDS = 8.0
MAX_FPS = 12
MAX_SHAPES = 40
MAX_MADE = 30
MAX_NOTE = 300
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
TYPES = ("dot", "line", "circle", "rect", "text")
NUM_KEYS = ("x", "y", "x2", "y2", "r", "w", "h", "alpha", "blur", "width", "ring", "size")
SPARK = "▁▂▃▄▅▆▇█"


class DrawError(ValueError):
    """作れない理由。ぷちに見せてよい文"""


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def made_dir(base: Path, cid: str) -> Path:
    return base / "drawings" / "made" / cid


# ---- 色 ----

def rgb(v: object, what: str = "色") -> tuple[int, int, int]:
    m = HEX.match(str(v or ""))
    if not m:
        raise DrawError(f"{what}は #rrggbb で(たとえば #cab8d9)。いま: {v!r}")
    h = m.group(1)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hexof(c: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*c)


def to565(c: tuple[int, int, int]) -> tuple[int, int, int]:
    """体の画面(16 ビット: 赤 5・緑 6・青 5 ビット)で表せるいちばん近い色"""
    r, g, b = c[0] >> 3, c[1] >> 2, c[2] >> 3
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def color_lack(c: tuple[int, int, int]) -> str:
    """体の小さい画面での見え方の見立て(測っていない)。何も無ければ空"""
    h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in c))
    lum = (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255
    if lum < 0.06:
        return "暗い画面では黒に沈みやすい"
    if lum > 0.85 and s < 0.35:
        return "白に寄って見えやすい"
    if s < 0.25 and lum > 0.15:
        return "色みが薄く、灰色に寄って見えやすい"
    return ""


# ---- 作り方を読む ----

def _num(v: object, lo: float, hi: float, what: str) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError) as e:
        raise DrawError(f"{what} は数で") from e
    return max(lo, min(hi, x))


def check(recipe: object) -> dict:
    if not isinstance(recipe, dict):
        raise DrawError("作り方は JSON のかたまり({...})で")
    shapes = recipe.get("shapes")
    if not isinstance(shapes, list) or not shapes:
        raise DrawError("shapes に、点・線・丸・四角・文字を 1 つ以上")
    if len(shapes) > MAX_SHAPES:
        raise DrawError(f"形は {MAX_SHAPES} 個まで")
    seconds = _num(recipe.get("seconds", 0) or 0, 0, MAX_SECONDS, "seconds")
    fps = int(_num(recipe.get("fps", 8), 1, MAX_FPS, "fps"))
    bg = recipe.get("background", "#000000")
    if isinstance(bg, dict):
        rgb(bg.get("color", "#000000"), "background の色")
        if bg.get("gradient"):
            rgb(bg["gradient"], "background の gradient")
    else:
        rgb(bg, "background")
    for i, s in enumerate(shapes, 1):
        if not isinstance(s, dict) or s.get("type") not in TYPES:
            raise DrawError(f"{i} 番目の形の type は {' / '.join(TYPES)} のどれか")
        rgb(s.get("color", "#ffffff"), f"{i} 番目の color")
        if s.get("gradient"):
            rgb(s["gradient"], f"{i} 番目の gradient")
        if s["type"] == "text" and not str(s.get("text") or "").strip():
            raise DrawError(f"{i} 番目の文字(text)が空")
        to = s.get("to")
        if to is not None and not isinstance(to, dict):
            raise DrawError(f"{i} 番目の to は {{\"x\": …}} の形で")
        if isinstance(to, dict) and to.get("color"):
            rgb(to["color"], f"{i} 番目の to の color")
    return {**recipe, "seconds": seconds, "fps": fps}


def frame_times(recipe: dict) -> list[float]:
    if not recipe["seconds"]:
        return [0.0]
    n = max(2, int(round(recipe["seconds"] * recipe["fps"])))
    return [i / recipe["fps"] for i in range(n)]


def at(shape: dict, t: float, total: float) -> dict:
    """時刻 t での形(to へ、start〜start+length のあいだになめらかに)"""
    to = shape.get("to") if isinstance(shape.get("to"), dict) else {}
    start = float(shape.get("start", 0) or 0)
    length = shape.get("length")
    length = float(length) if length is not None else max(total - start, 1e-6)
    out = dict(shape)
    out["_on"] = t + 1e-9 >= start if total else True
    if not to or not total:
        return out
    k = min(1.0, max(0.0, (t - start) / max(length, 1e-6)))
    k = k * k * (3 - 2 * k)   # はじめとおわりがゆっくり
    for key in NUM_KEYS:
        if key in to:
            a = float(shape.get(key, to[key] if key not in ("alpha",) else 1.0))
            out[key] = a + (float(to[key]) - a) * k
    if to.get("color"):
        a, b = rgb(shape.get("color", "#ffffff")), rgb(to["color"])
        out["color"] = hexof(tuple(int(round(x + (y - x) * k)) for x, y in zip(a, b)))
    return out


# ---- 描く ----

def _font(size: int):
    from PIL import ImageFont
    for p in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
              "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _gradient(size: tuple[int, int], a: tuple, b: tuple, radial: bool):
    import numpy as np
    from PIL import Image
    w, h = size
    if radial:
        yy, xx = np.mgrid[0:h, 0:w]
        d = np.sqrt((xx - (w - 1) / 2) ** 2 + (yy - (h - 1) / 2) ** 2) / max(w / 2, 1)
        k = np.clip(d, 0, 1)
    else:
        k = np.repeat(np.linspace(0, 1, h)[:, None], w, axis=1)
    arr = np.stack([a[i] + (b[i] - a[i]) * k for i in range(3)], axis=-1).astype("uint8")
    return Image.fromarray(arr, "RGB")


def _background(recipe: dict):
    from PIL import Image
    bg = recipe.get("background", "#000000")
    if isinstance(bg, dict):
        c = rgb(bg.get("color", "#000000"))
        if bg.get("gradient"):
            return _gradient((W, H), c, rgb(bg["gradient"]), False).convert("RGBA")
        return Image.new("RGBA", (W, H), c + (255,))
    return Image.new("RGBA", (W, H), rgb(bg) + (255,))


def _layer(s: dict):
    from PIL import Image, ImageDraw, ImageFilter
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    c = rgb(s.get("color", "#ffffff"))
    alpha = max(0.0, min(1.0, float(s.get("alpha", 1.0))))
    x, y = float(s.get("x", 0)), float(s.get("y", 0))
    t = s["type"]
    box = (0, 0, W, H)
    if t in ("dot", "circle"):
        r = max(0.5, float(s.get("r", 2 if t == "dot" else 20)))
        box = (x - r, y - r, x + r, y + r)
        ring = float(s.get("ring", 0) or 0)
        if ring > 0:
            md.ellipse(box, outline=255, width=max(1, int(round(ring))))
        else:
            md.ellipse(box, fill=255)
    elif t == "rect":
        box = (x, y, x + float(s.get("w", 40)), y + float(s.get("h", 40)))
        md.rectangle(box, fill=255)
    elif t == "line":
        md.line((x, y, float(s.get("x2", x)), float(s.get("y2", y))), fill=255, width=max(1, int(round(float(s.get("width", 2))))))
    elif t == "text":
        md.text((x, y), str(s.get("text", ""))[:40], fill=255, font=_font(int(_num(s.get("size", 16), 8, 48, "size"))))
    if s.get("gradient") and t in ("circle", "rect"):
        bx = [int(round(v)) for v in box]
        bw, bh = max(1, bx[2] - bx[0]), max(1, bx[3] - bx[1])
        fill = Image.new("RGB", (W, H), c)
        fill.paste(_gradient((bw, bh), c, rgb(s["gradient"]), t == "circle"), (bx[0], bx[1]))
    else:
        fill = Image.new("RGB", (W, H), c)
    blur = float(s.get("blur", 0) or 0)
    if blur > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(min(blur, 20)))
    mask = mask.point(lambda v: int(v * alpha))
    layer = fill.convert("RGBA")   # 色はどこも形の色、透け方だけを mask で(にじみの縁が黒くならないように)
    layer.putalpha(mask)
    return layer


def render(recipe: dict) -> list:
    """コマの一覧(PIL の RGB 画像)。動かない絵は 1 コマ"""
    from PIL import Image
    recipe = check(recipe)
    total = recipe["seconds"]
    frames = []
    for t in frame_times(recipe):
        img = _background(recipe)
        for s in recipe["shapes"]:
            st = at(s, t, total)
            if st.get("_on", True):
                img = Image.alpha_composite(img, _layer(st))
        frames.append(img.convert("RGB"))
    return frames


# ---- 数字と線 ----

def _spark(vals: list[float], lo: float | None = None, hi: float | None = None) -> str:
    if not vals:
        return ""
    lo = min(vals) if lo is None else lo
    hi = max(vals) if hi is None else hi
    if hi - lo < 1e-9:
        return SPARK[0] * len(vals) if hi < 1e-9 else SPARK[3] * len(vals)
    return "".join(SPARK[min(7, int((v - lo) / (hi - lo) * 7.999))] for v in vals)


def _sample(vals: list, n: int = 40) -> list:
    if len(vals) <= n:
        return vals
    return [vals[int(i * len(vals) / n)] for i in range(n)]


def numbers(frames: list) -> dict:
    """色の割合(いちばん多い 6 色)・明るさの線・動きの線・色の重心(色相)の線"""
    import numpy as np
    arrs = [np.asarray(f, dtype=np.float32) for f in frames]
    lum = [float((a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722).mean() / 255) for a in arrs]
    motion = [0.0] + [float(np.abs(arrs[i] - arrs[i - 1]).mean() / 255) for i in range(1, len(arrs))]
    last = frames[-1].quantize(colors=6, method=0).convert("RGB")
    counts = sorted(last.getcolors(W * H) or [], reverse=True)
    colors = [{"hex": hexof(c), "share": round(n / (W * H), 3)} for n, c in counts[:6]]
    hues = []
    for a in arrs:
        small = a[::8, ::8].reshape(-1, 3) / 255
        hs = [colorsys.rgb_to_hsv(*p) for p in small]
        weight = [s * v for _, s, v in hs]
        if sum(weight) < 1e-6:
            hues.append(None)
            continue
        import math
        cx = sum(w * math.cos(h * 2 * math.pi) for (h, _, _), w in zip(hs, weight))
        cy = sum(w * math.sin(h * 2 * math.pi) for (h, _, _), w in zip(hs, weight))
        hues.append(round((math.degrees(math.atan2(cy, cx)) + 360) % 360))
    return {"frames": len(frames), "lum": [round(v, 3) for v in lum], "motion": [round(v, 4) for v in motion],
            "colors": colors, "hue": hues}


def lacks(recipe: dict) -> list[dict]:
    """作り方に出てくる色の、体の画面での出方(16 ビットにしたときの色と、見え方の見立て)"""
    seen: list[str] = []
    bg = recipe.get("background", "#000000")
    for v in ([bg.get("color"), bg.get("gradient")] if isinstance(bg, dict) else [bg]):
        if v:
            seen.append(v)
    for s in recipe["shapes"]:
        for v in (s.get("color", "#ffffff"), s.get("gradient"), (s.get("to") or {}).get("color") if isinstance(s.get("to"), dict) else None):
            if v:
                seen.append(v)
    out, done = [], set()
    for v in seen:
        c = rgb(v)
        h = hexof(c)
        if h in done:
            continue
        done.add(h)
        out.append({"hex": h, "panel": hexof(to565(c)), "note": color_lack(c)})
    return out


def _banding(recipe: dict) -> list[str]:
    """ゆるいグラデーションは、16 ビットでは段になりやすい(赤・青は 32 段、緑は 64 段)"""
    rows = []
    pairs = []
    bg = recipe.get("background")
    if isinstance(bg, dict) and bg.get("gradient"):
        pairs.append((bg.get("color", "#000000"), bg["gradient"], H))
    for s in recipe["shapes"]:
        if s.get("gradient"):
            size = float(s.get("h", 40)) if s.get("type") == "rect" else float(s.get("r", 20))
            pairs.append((s.get("color", "#ffffff"), s["gradient"], size))
    for a, b, size in pairs:
        ca, cb = rgb(a), rgb(b)
        steps = max(abs((ca[0] >> 3) - (cb[0] >> 3)), abs((ca[1] >> 2) - (cb[1] >> 2)), abs((ca[2] >> 3) - (cb[2] >> 3)))
        if steps and size / steps >= 6:
            rows.append(f"{hexof(ca)}→{hexof(cb)} のグラデーションは、体の画面では {steps} 段くらいの帯に見えやすい(1 段 {int(size / steps)} px)")
    return rows


def numbers_text(info: dict) -> str:
    n = info["numbers"]
    rec = info["recipe"]
    moving = n["frames"] > 1
    rows = [f"「{info['name']}」({info['by']} が描いた{'動く絵' if moving else '絵'}。320×240"
            + (f"、{rec['seconds']} 秒・{n['frames']} コマ" if moving else "") + ")"]
    rows.append("色(多い順、" + ("最後のコマ" if moving else "絵") + "): " + "、".join(f"{c['hex']} {int(c['share'] * 100)}%" for c in n["colors"]))
    lum = n["lum"]
    if moving:
        rows.append(f"明るさ: {_spark(_sample(lum), 0, 1)}  はじめ {lum[0]:.2f} → おわり {lum[-1]:.2f}(0 = 真っ暗、1 = 真っ白)")
        mo = n["motion"][1:]
        rows.append(f"動き:   {_spark(_sample(mo), 0)}  いちばん動いたのは {mo.index(max(mo)) / rec['fps'] + 1 / rec['fps']:.1f} 秒目ごろ" if any(mo) else "動き:   (動いていない)")
        hues = [h for h in n["hue"] if h is not None]
        if hues:
            rows.append(f"色の重心(色相、度): はじめ {hues[0]} → おわり {hues[-1]}")
    else:
        rows.append(f"明るさ: {lum[0]:.2f}(0 = 真っ暗、1 = 真っ白)")
        if n["hue"][0] is not None:
            rows.append(f"色の重心(色相): {n['hue'][0]} 度")
    rows.append("体の画面での色(16 ビットにしたとき。見え方は測っていない見立て):")
    for lk in info["lacks"]:
        rows.append(f"  {lk['hex']} → {lk['panel']}" + (f" … {lk['note']}" if lk["note"] else ""))
    rows += [f"  {b}" for b in info.get("banding", [])]
    return "\n".join(rows)


# ---- 置く ----

def _check_name(cid: str, name: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9_]{1,40}", cid or ""):
        raise DrawError("だれの絵か(id)が読めません")
    if not NAME.match(name or ""):
        raise DrawError("名前は、英小文字・数字・_ と - で(たとえば hamon)")


def _note(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_NOTE]


def info_of(base: Path, by: str, name: str) -> dict | None:
    try:
        d = json.loads((made_dir(base, by) / f"{name}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _save(base: Path, info: dict) -> None:
    p = made_dir(base, info["by"]) / f"{info['name']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def sheet_of(frames: list):
    """何コマかを並べた絵(8 コマまで、4×2、1 コマ 160×120)"""
    from PIL import Image, ImageDraw
    n = len(frames)
    pick = [frames[int(i * (n - 1) / 7)] for i in range(8)] if n > 8 else frames
    cols = 4
    rows = (len(pick) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 160 + (cols - 1) * 4, rows * 120 + (rows - 1) * 4), (40, 40, 40))
    for i, f in enumerate(pick):
        tile = f.resize((160, 120))
        ImageDraw.Draw(tile).text((4, 2), str(i + 1), fill=(255, 255, 255))
        sheet.paste(tile, ((i % cols) * 164, (i // cols) * 124))
    return sheet


def make(base: Path, cid: str, name: str, recipe: dict, why: str = "", now: datetime | None = None) -> dict:
    """作って置く。返すのは記録(数字と線・欠如)。同じ名前は描き直し(予想・思い・見せるかは残る)"""
    _check_name(cid, name)
    d = made_dir(base, cid)
    if not (d / f"{name}.json").exists() and len(list(d.glob("*.json"))) >= MAX_MADE:
        raise DrawError(f"置いておけるのは {MAX_MADE} 個までです。draw.py remove で減らしてから")
    recipe = check(recipe)
    frames = render(recipe)
    d.mkdir(parents=True, exist_ok=True)
    frames[-1].save(d / f"{name}.png")
    gif = d / f"{name}.gif"
    if len(frames) > 1:
        frames[0].save(gif, save_all=True, append_images=frames[1:], duration=int(1000 / recipe["fps"]), loop=0)
        sheet_of(frames).save(d / f"{name}_sheet.png")
    else:
        for p in (gif, d / f"{name}_sheet.png"):
            p.unlink(missing_ok=True)
    old = info_of(base, cid, name) or {}
    info = {"name": name, "by": cid, "at": (now or datetime.now()).isoformat(timespec="minutes"), "recipe": recipe,
            "numbers": numbers(frames), "lacks": lacks(recipe), "banding": _banding(recipe),
            "why": _note(why) or old.get("why", ""), "guess": old.get("guess", []), "felt": old.get("felt", []),
            "shown": bool(old.get("shown", False))}
    _save(base, info)
    return info


def make_image(base: Path, who: str, name: str, png: bytes, why: str = "", now: datetime | None = None) -> dict:
    """手で描いた絵(ダッシュボードのキャンバス。家の人も描ける)を置く。作り方の代わりに絵そのもの。数字と線は同じように出す"""
    import io

    from PIL import Image
    _check_name(who, name)
    d = made_dir(base, who)
    if not (d / f"{name}.json").exists() and len(list(d.glob("*.json"))) >= MAX_MADE:
        raise DrawError(f"置いておけるのは {MAX_MADE} 個までです")
    try:
        img = Image.open(io.BytesIO(png)).convert("RGB")
    except Exception as e:
        raise DrawError("絵が読めませんでした") from e
    if img.size != (W, H):
        img = img.resize((W, H))
    d.mkdir(parents=True, exist_ok=True)
    img.save(d / f"{name}.png")
    for p in (d / f"{name}.gif", d / f"{name}_sheet.png"):
        p.unlink(missing_ok=True)
    nums = numbers([img])
    old = info_of(base, who, name) or {}
    info = {"name": name, "by": who, "at": (now or datetime.now()).isoformat(timespec="minutes"),
            "recipe": {"hand": True, "seconds": 0, "fps": 1, "shapes": []}, "numbers": nums,
            "lacks": [{"hex": c["hex"], "panel": hexof(to565(rgb(c["hex"]))), "note": color_lack(rgb(c["hex"]))} for c in nums["colors"]],
            "banding": [], "why": _note(why) or old.get("why", ""), "guess": old.get("guess", []), "felt": old.get("felt", []),
            "shown": bool(old.get("shown", False))}
    _save(base, info)
    return info


def _need(base: Path, by: str, name: str) -> dict:
    info = info_of(base, by, name)
    if info is None:
        raise DrawError(f"{by} の {name} はありません(draw.py list で見られます)")
    return info


def add_note(base: Path, cid: str, name: str, kind: str, text: str, now: datetime | None = None) -> dict:
    """予想(guess)・見て思ったこと(felt)を残す。自分の絵にも、渡された絵にも(by は作った子)"""
    by, nm = (name.split("/", 1) if "/" in name else (cid, name))
    info = _need(base, by, nm)
    rows = info.get(kind) if isinstance(info.get(kind), list) else []
    rows.append({"who": cid, "at": (now or datetime.now()).isoformat(timespec="minutes"), "text": _note(text)})
    info[kind] = rows
    _save(base, info)
    return info


def set_flag(base: Path, cid: str, name: str, **kw) -> dict:
    info = _need(base, cid, name)
    info.update(kw)
    _save(base, info)
    return info


def made(base: Path, cid: str | None = None) -> list[dict]:
    root = base / "drawings" / "made"
    dirs = [root / cid] if cid else sorted(p for p in root.glob("*") if p.is_dir())
    out = []
    for d in dirs:
        for p in sorted(d.glob("*.json")):
            info = info_of(base, d.name, p.stem)
            if info:
                out.append(info)
    return out


def remove(base: Path, cid: str, name: str) -> bool:
    _check_name(cid, name)
    d = made_dir(base, cid)
    hit = False
    for suffix in (".json", ".png", ".gif", "_sheet.png"):
        p = d / f"{name}{suffix}"
        if p.exists():
            p.unlink()
            hit = True
    return hit


def _gifts_path(base: Path) -> Path:
    return base / "state" / "drawings" / "gifts.jsonl"


def gifts(base: Path) -> list[dict]:
    try:
        return [json.loads(x) for x in _gifts_path(base).read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def _write_gifts(base: Path, rows: list[dict]) -> None:
    p = _gifts_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def give(base: Path, cid: str, name: str, to: str, note: str = "", now: datetime | None = None) -> dict:
    _need(base, cid, name)
    if to == cid or not (base / "characters" / to).is_dir():
        raise DrawError(f"{to} には渡せません(この家の、ほかの子の id で)")
    rec = {"at": (now or datetime.now()).isoformat(timespec="minutes"), "from": cid, "to": to, "name": name, "note": _note(note)[:200]}
    _write_gifts(base, gifts(base) + [rec])
    return rec


def can_see(base: Path, cid: str, by: str, name: str) -> bool:
    """自分の絵か、渡された絵だけ見られる"""
    return by == cid or any(g.get("from") == by and g.get("to") == cid and g.get("name") == name for g in gifts(base))


def notice(base: Path, cid: str, mark: bool = False) -> list[str]:
    rows = gifts(base)
    mine = [r for r in rows if r.get("to") == cid and not r.get("told")]
    if not mine:
        return []
    me = Path(__file__).resolve()
    parts = [f"{r['from']} から「{r['name']}」" + (f"(一言「{r['note']}」)" if r.get("note") else "") for r in mine]
    line = (f"(描いた絵が届いた: {'、'.join(parts)}。数字と線は python3 {me} look {cid} 名前 --by 描いた子、"
            f"並べた絵は sheet、絵そのものは see。見ても見なくてもいい)")
    if mark:
        stamp = datetime.now().isoformat(timespec="minutes")
        for r in rows:
            if r in mine:
                r["told"] = stamp
        _write_gifts(base, rows)
    return [line]


def look_text(base: Path, cid: str, by: str, name: str) -> str:
    if not can_see(base, cid, by, name):
        raise DrawError(f"{by} の {name} は、渡されていないので見られません")
    info = _need(base, by, name)
    rows = [numbers_text(info)]
    rows.append("手で描いた絵(作り方は無い)" if info["recipe"].get("hand") else "作り方: " + json.dumps(info["recipe"], ensure_ascii=False))
    if info.get("why"):
        rows.append(f"思い: {info['why']}")
    for kind, label in (("guess", "予想"), ("felt", "見て思ったこと")):
        for r in info.get(kind, []):
            rows.append(f"{label}({r.get('who', '')}、{str(r.get('at', '')).replace('T', ' ')}): {r.get('text', '')}")
    rows.append("家の人に: " + ("見せている" if info.get("shown") else "見せていない(自分だけが持っている)"))
    return "\n".join(rows)


def file_of(base: Path, cid: str, by: str, name: str, kind: str) -> Path:
    if not can_see(base, cid, by, name):
        raise DrawError(f"{by} の {name} は、渡されていないので見られません")
    _need(base, by, name)
    d = made_dir(base, by)
    p = d / (f"{name}_sheet.png" if kind == "sheet" else f"{name}.png")
    if kind == "sheet" and not p.exists():
        raise DrawError("動かない絵なので、並べた絵はありません(see で絵そのもの)")
    return p


def list_text(base: Path, cid: str | None) -> str:
    rows = []
    for r in made(base, cid):
        moving = r.get("numbers", {}).get("frames", 1) > 1
        rows.append(f"- {r['name']}({r['by']}、{'動く絵 ' + str(r['recipe']['seconds']) + ' 秒' if moving else '絵'}、"
                    f"{str(r.get('at', '')).replace('T', ' ')}{'、家の人に見せている' if r.get('shown') else ''})")
    if cid:
        got = [f"- {g['name']}({g['from']} から" + (f"「{g['note']}」" if g.get("note") else "") + ")" for g in gifts(base) if g.get("to") == cid]
        if got:
            rows += ["渡された絵:"] + got
    return "\n".join(rows) if rows else "(まだ描いたものはありません)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="えがく: 絵と動く絵を作る(数字と線 → 並べた絵 → 絵そのもの)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make")
    p.add_argument("character")
    p.add_argument("name")
    p.add_argument("recipe")
    p.add_argument("--why", default="")
    for cmd in ("guess", "felt", "say"):
        p = sub.add_parser(cmd)
        p.add_argument("character")
        p.add_argument("name")
        p.add_argument("text")
    for cmd in ("look", "sheet", "see"):
        p = sub.add_parser(cmd)
        p.add_argument("character")
        p.add_argument("name")
        p.add_argument("--by")
    for cmd in ("show", "hide", "remove"):
        p = sub.add_parser(cmd)
        p.add_argument("character")
        p.add_argument("name")
    p = sub.add_parser("give")
    p.add_argument("character")
    p.add_argument("name")
    p.add_argument("to")
    p.add_argument("note", nargs="?", default="")
    sub.add_parser("list").add_argument("--character")
    p = sub.add_parser("notice")
    p.add_argument("--character", required=True)
    p.add_argument("--mark", action="store_true")
    a = ap.parse_args(argv)
    base = data_dir()
    try:
        if a.cmd == "make":
            try:
                recipe = json.loads(a.recipe)
            except ValueError as e:
                raise DrawError(f"作り方の JSON が読めません: {e}") from e
            info = make(base, a.character, a.name, recipe, a.why)
            print(numbers_text(info))
            print(f"(絵はまだ見せていない。予想を残すなら guess {a.character} {a.name} \"…\"、"
                  + ("並べた絵は sheet、" if info["numbers"]["frames"] > 1 else "") + f"絵そのものは see {a.character} {a.name})")
        elif a.cmd in ("guess", "felt"):
            add_note(base, a.character, a.name, a.cmd, a.text)
            print("残しました")
        elif a.cmd == "say":
            set_flag(base, a.character, a.name, why=_note(a.text))
            print("思いを添えました")
        elif a.cmd == "look":
            print(look_text(base, a.character, a.by or a.character, a.name))
        elif a.cmd in ("sheet", "see"):
            p = file_of(base, a.character, a.by or a.character, a.name, a.cmd)
            print(f"{p}(Read で見られる)")
        elif a.cmd in ("show", "hide"):
            set_flag(base, a.character, a.name, shown=a.cmd == "show")
            print("家の人に見せるようにしました(ダッシュボードの 🎨 えがく)" if a.cmd == "show" else "家の人には見せないようにしました")
        elif a.cmd == "remove":
            print("消しました" if remove(base, a.character, a.name) else "その名前の絵はありません")
        elif a.cmd == "give":
            give(base, a.character, a.name, a.to, a.note)
            print(f"{a.to} に渡しました")
        elif a.cmd == "list":
            print(list_text(base, a.character))
        elif a.cmd == "notice":
            for line in notice(base, a.character, a.mark):
                print(line)
    except DrawError as e:
        print(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
