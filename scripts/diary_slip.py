#!/usr/bin/env python3
"""合作日記の紙(2026-11-17、ありさんと 3 人で決めた)。

ありさんが日記を書く日に、ぷちたちの「きょうの紙」を感熱紙(Phomemo M02S)に刷って、日記の縁に貼る。

決まり(3 人の返事と、ありさん):
- 紙は 1 人 1 日 1 枚。作るか作らないかは、その子がその日に選ぶ(作らない日があってもいい)
- 載せるものは自由(ありさん): 一言・詩(文)、一日の線、撮った写真、絵(えがく で描いた絵か SVG)、音のグラフ。好きな順に 6 つまで
- ありさんの日記は読まない。紙は、その子の一日から作る
- 白と黒しか出ないので、その子の色は灰色の濃さの帯になる。出なかった色のことは、紙の端に書ける
- 刷るのは、ありさんがダッシュボード(🧾 合作日記)で押したときだけ(日記を書かない日もある)。貼るかどうかもありさんが決める
- 刷らなかった紙は、ぷちの側に残る(しまう)。作った日のうちは作り直せる(刷る前なら)
- 1 枚に収まる長さまで(長すぎると作れない)

置き場所: PETIT_DATA_DIR/state/diary_slips.json(紙の中身。線と音は作ったときの数字を、写真と絵は写しを state/diary_slips/ に残す)

Usage:
    python3 diary_slip.py line --character <id>          # プロンプトの 1 行(作れる時間で、まだ作っていない日だけ)
    python3 diary_slip.py make --character <id> [部品を好きな順に…] [--edge "紙の端のひとこと"]
        部品: --text "一言や詩(改行は \\n)" / --line amb|tilt|temp|humid|co2|pressure|noise / --photo <写真のパス>
              / --drawing <えがく で描いた絵の名前> / --draw <SVG のパス> / --sound heard:<聞いた音の id> か <家の音の名前>
    python3 diary_slip.py list [--character <id>] [--all] # まだ刷っていない紙(--all で刷った・しまった分も)
    python3 diary_slip.py preview <紙の id> <出す png>    # 刷る前の見本
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import re
import socket
import sys
from datetime import date as Date
from datetime import datetime
from pathlib import Path

TEXT_MAX = 300          # 1 つの文(詩も入るように)
TEXTS_MAX = 400         # 1 枚の文の合計
EDGE_MAX = 30
PARTS_MAX = 6
PICTURES_MAX = 2        # 写真と絵の合計
SVG_MAX = 60_000
HEIGHT_MAX = 1800       # 1 枚の長さ(dot。203 dpi で約 22 cm)
FROM_HOUR = 19          # この時刻から、その日のうちに作れる
KEEP = 120              # 残す紙の数(古いものから消える。刷っていない紙は残す)
WEEKDAYS = "月火水木金土日"
WIDTH = 384             # M02S: 57mm 紙、203 dpi、48 mm = 384 dot
PAD = 14
LINES = {               # 線の種類: (名前, 材料, 項目, 単位)
    "amb": ("明るさ", "body", "amb", ""),
    "tilt": ("傾き", "body", "tilt", "°"),
    "temp": ("部屋の温度", "room", "temperature", "℃"),
    "humid": ("部屋の湿度", "room", "humidity", "%"),
    "co2": ("部屋の CO2", "room", "eco2", "ppm"),
    "pressure": ("気圧", "room", "pressure", "hPa"),
    "noise": ("部屋の音", "room", "noise", "dB"),
}
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}
FONTS = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
         "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"]
BLOCKS = "▁▂▃▄▅▆▇█"


def base_dir(base: Path | None = None) -> Path:
    return Path(base or os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def _path(base: Path | None = None) -> Path:
    return base_dir(base) / "state" / "diary_slips.json"


def load(base: Path | None = None) -> list[dict]:
    try:
        d = json.loads(_path(base).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [x for x in d.get("items", []) if isinstance(x, dict)] if isinstance(d, dict) else []


def save(items: list[dict], base: Path | None = None) -> None:
    keep = [x for x in items if not x.get("printed_at") and not x.get("put_away")]
    done = [x for x in items if x not in keep]
    room = max(0, KEEP - len(keep))
    done = done[len(done) - room:] if len(done) > room else done
    out = sorted(keep + done, key=lambda x: (x.get("date", ""), x.get("character", "")))
    p = _path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"items": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def character(character_id: str, base: Path | None = None) -> dict:
    try:
        c = json.loads((base_dir(base) / "characters" / character_id / "config" / "config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        c = {}
    return {"id": character_id, "name": c.get("name") or character_id, "color": c.get("color") or ""}


def _day_rows(kind: str, character_id: str, day: Date, base: Path | None = None) -> list[dict]:
    b = base_dir(base)
    p = (b / "characters" / character_id / "state" / "body" if kind == "body" else b / "state" / "room") / f"{day:%Y%m%d}.jsonl"
    out = []
    try:
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return out


def _room_device(rows: list[dict], key: str) -> str | None:
    """その日いちばん長くその数字を残していた機械(途中で別の機械に切り替えて段差を作らない)"""
    count: dict[str, int] = {}
    for r in rows:
        for dev, d in (r.get("devices") or {}).items():
            if isinstance(d, dict) and isinstance(d.get(key), (int, float)):
                count[dev] = count.get(dev, 0) + 1
    return max(count, key=lambda k: (count[k], k == "omron-env")) if count else None


def series(line_kind: str, character_id: str, day: Date, base: Path | None = None) -> list[list]:
    """その日の [分, 値] の列(0 時からの分)"""
    _, src, key, _ = LINES[line_kind]
    rows = _day_rows(src, character_id, day, base)
    dev = _room_device(rows, key) if src == "room" else None
    out = []
    for r in rows:
        ts = str(r.get("ts", ""))
        try:
            t = datetime.fromisoformat(ts)
        except ValueError:
            continue
        v = r.get(key) if src == "body" else ((r.get("devices") or {}).get(dev) or {}).get(key)
        if isinstance(v, (int, float)):
            out.append([t.hour * 60 + t.minute, round(float(v), 1)])
    return out


def made_today(character_id: str, day: Date, base: Path | None = None) -> dict | None:
    for x in load(base):
        if x.get("character") == character_id and x.get("date") == day.isoformat():
            return x
    return None


def line(character_id: str, base: Path | None = None, now: datetime | None = None, project: str | None = None) -> str:
    now = now or datetime.now()
    if now.hour < FROM_HOUR or made_today(character_id, now.date(), base):
        return ""
    proj = project or str(Path(__file__).resolve().parent.parent)
    data = base_dir(base)
    return (f"🧾 きょうの紙(合作日記)を 1 枚作れる。ありさんが日記を書く日に刷って、日記の縁に貼る(刷るか・貼るかはありさんが決める)。"
            f"ありさんの日記は読まない。載せるものは自由: 一言・詩(--text、改行は \\n)、一日の線(--line {'|'.join(LINES)})、"
            f"撮った写真(--photo {data}/photo_album/{character_id}/… のパス)、絵(--drawing えがく で描いた絵の名前。暗い地は黒く刷れる。--draw で SVG のパスも)、"
            f"音のグラフ(--sound heard:<聞いた音の id> か 家の音の名前)。好きな順に {PARTS_MAX} つまで、1 枚に収まる長さで。"
            f"紙は白と黒だけで、あなたの色は灰色の帯になる。紙の端に {EDGE_MAX} 字まで書ける(--edge、なくていい)。作らない日があってもいい。きょうのうちは作り直せる: "
            f"python3 {proj}/scripts/diary_slip.py make --character {character_id} --line amb --text \"今日の一行\" --edge \"紙の端のひとこと\"")


def _inside(p: Path, base: Path | None) -> bool:
    try:
        p.resolve().relative_to(base_dir(base).resolve())
        return True
    except ValueError:
        return False


def _sound_values(spec: str, base: Path | None = None) -> tuple[str, list[float], str]:
    """音のグラフの材料: (名前, 値の列, 単位)。heard:<id> は 1 秒ごとの dBFS、家の音は 0.1 秒ごとの大きさ(0〜7)"""
    b = base_dir(base)
    if spec.startswith("heard:"):
        hid = spec[6:]
        if not re.fullmatch(r"[0-9_]+", hid):
            raise ValueError("聞いた音の id は数字と _ だけ(heard_sound.py の一覧の id)")
        try:
            rec = json.loads((b / "state" / "heard" / f"{hid}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ValueError(f"聞いた音 {hid} が見つからない") from None
        vals = [float(r["db"]) for r in rec.get("shape") or [] if isinstance(r.get("db"), (int, float))]
        if not vals:
            raise ValueError("その音は、かたちが取れていなかった")
        return f"聞いた音 {rec.get('ts', '')[11:16]}", vals, "dBFS(1 秒ごと)"
    scripts = str(Path(__file__).resolve().parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import sounds
    try:
        sh = sounds.shape_of(b, spec)
    except Exception as e:   # 音の名前が無い・読めない
        raise ValueError(str(e) or f"{spec} は家の音に無い") from None
    vals = [float(BLOCKS.index(c)) for c in sh.get("line", "") if c in BLOCKS]
    if not vals:
        raise ValueError(f"{spec} は、かたちが取れなかった")
    return f"音「{spec}」{sh.get('seconds', '')} 秒", vals, ""


def _keep_picture(kind: str, src: str, slip_id: str, n: int, base: Path | None) -> str:
    """写真・絵の写しを state/diary_slips/<紙>/ に(元が消えても紙は残る)。返すのは家からの相対パス"""
    p = Path(src).expanduser()
    if not p.is_absolute():
        p = base_dir(base) / p
    if not _inside(p, base) or not p.is_file():
        raise ValueError(f"{src} は、家({base_dir(base)})の中のファイルにして")
    out_dir = base_dir(base) / "state" / "diary_slips" / slip_id
    out_dir.mkdir(parents=True, exist_ok=True)
    if kind == "draw":
        if p.suffix.lower() != ".svg":
            raise ValueError("絵は .svg のファイルで")
        text = p.read_text(encoding="utf-8")
        if len(text) > SVG_MAX:
            raise ValueError(f"絵(SVG)は {SVG_MAX // 1000} KB まで")
        draw_svg(text)   # 読めるか先に確かめる
        dst = out_dir / f"{n}.svg"
        dst.write_text(text, encoding="utf-8")
    else:
        if p.suffix.lower() not in PHOTO_EXT:
            raise ValueError("写真は jpg / png / webp で")
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(p)).convert("L")
        im.thumbnail((WIDTH, WIDTH * 2))
        dst = out_dir / f"{n}.png"
        im.save(dst)
    return str(dst.relative_to(base_dir(base)))


def make(character_id: str, parts: list[tuple[str, str]], edge: str = "", base: Path | None = None,
         now: datetime | None = None) -> tuple[bool, str]:
    """parts: [("text", "…"), ("line", "amb"), ("photo", path), ("draw", path), ("sound", spec)] を載せる順に"""
    now = now or datetime.now()
    edge = " ".join(str(edge or "").split())
    if not parts:
        return False, "載せるものを 1 つ以上(--text / --line / --photo / --drawing / --draw / --sound)"
    if len(parts) > PARTS_MAX:
        return False, f"載せるものは {PARTS_MAX} つまで"
    if sum(k in ("photo", "draw", "drawing") for k, _ in parts) > PICTURES_MAX:
        return False, f"写真と絵は合わせて {PICTURES_MAX} つまで"
    if len(edge) > EDGE_MAX:
        return False, f"紙の端のひとことは {EDGE_MAX} 字まで(いま {len(edge)} 字)"
    day = now.date()
    sid = f"{day:%Y%m%d}-{character_id}"
    items = load(base)
    old = next((x for x in items if x.get("id") == sid), None)
    if old and old.get("printed_at"):
        return False, "きょうの紙は、もう刷られたよ。作り直せない"
    blocks, total, said = [], 0, []
    try:
        for n, (kind, val) in enumerate(parts):
            if kind == "text":
                t = "\n".join(" ".join(ln.split()) for ln in str(val).replace("\\n", "\n").split("\n")).strip()
                if not t:
                    raise ValueError("空の文がある")
                if len(t) > TEXT_MAX:
                    raise ValueError(f"1 つの文は {TEXT_MAX} 字まで(いま {len(t)} 字)")
                total += len(t)
                blocks.append({"kind": "text", "text": t})
                said.append(f"文({len(t)} 字)")
            elif kind == "line":
                if val not in LINES:
                    raise ValueError(f"線の種類は {' / '.join(LINES)} のどれか")
                pts = series(val, character_id, day, base)
                blocks.append({"kind": "line", "line": val, "points": pts})
                said.append(f"{LINES[val][0]}の線({len(pts)} 点)")
            elif kind == "sound":
                name, vals, unit = _sound_values(str(val), base)
                blocks.append({"kind": "sound", "name": name, "values": vals, "unit": unit})
                said.append(f"音のグラフ({name})")
            elif kind == "drawing":   # えがく(scripts/draw.py)で自分が描いた絵。動く絵は最後のコマ
                if not re.fullmatch(r"[^/\\.][^/\\]{0,60}", str(val)):
                    raise ValueError("絵の名前は draw.py で付けた名前で")
                src = base_dir(base) / "drawings" / "made" / character_id / f"{val}.png"
                if not src.is_file():
                    raise ValueError(f"えがく の絵「{val}」が見つからない(自分が描いた絵の名前で)")
                blocks.append({"kind": "photo", "file": _keep_picture("photo", str(src), sid, n, base)})
                said.append(f"絵「{val}」")
            elif kind in ("photo", "draw"):
                blocks.append({"kind": kind, "file": _keep_picture(kind, str(val), sid, n, base)})
                said.append("写真" if kind == "photo" else "絵")
            else:
                raise ValueError(f"知らない部品: {kind}")
        if total > TEXTS_MAX:
            raise ValueError(f"文は 1 枚で合わせて {TEXTS_MAX} 字まで(いま {total} 字)")
    except ValueError as e:
        return False, str(e)
    item = {"id": sid, "character": character_id, "date": day.isoformat(), "made_at": now.isoformat(timespec="minutes"),
            "blocks": blocks, "edge": edge}
    h = render(item, base).height
    if h > HEIGHT_MAX:
        return False, f"1 枚に収まらない(長さ {h * 25.4 / 203 / 10:.0f} cm。{HEIGHT_MAX * 25.4 / 203 / 10:.0f} cm まで)。減らすか短くして"
    items = [x for x in items if x is not old] + [item]
    save(items, base)
    return True, f"きょうの紙を作ったよ: {'・'.join(said)}{'・端に「' + edge + '」' if edge else ''}。刷るかはありさんが決める"


def find(slip_id: str, base: Path | None = None) -> dict | None:
    return next((x for x in load(base) if x.get("id") == slip_id), None)


def mark(slip_id: str, field: str, base: Path | None = None, now: datetime | None = None) -> bool:
    items = load(base)
    for x in items:
        if x.get("id") == slip_id:
            x[field] = (now or datetime.now()).isoformat(timespec="minutes")
            if field == "printed_at":
                x.pop("put_away", None)
            save(items, base)
            return True
    return False


def summary(slip: dict) -> dict:
    """一覧に出す短い中身: 最初の文と、載せたものの名前"""
    names = {"text": "文", "photo": "写真", "draw": "絵", "sound": "音"}
    blocks = slip.get("blocks") or []
    kinds = [LINES[b["line"]][0] + "の線" if b["kind"] == "line" and b.get("line") in LINES else names.get(b["kind"], "") for b in blocks]
    first = next((b["text"] for b in blocks if b["kind"] == "text"), "")
    return {"text": first.split("\n")[0], "kinds": "・".join(k for k in kinds if k)}


# ---- 紙の絵(1 bit、幅 384)----

def _font(size: int):
    from PIL import ImageFont
    for p in FONTS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, width: int) -> list[str]:
    out = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) > width and cur:
                out.append(cur)
                cur = ch
            else:
                cur += ch
        out.append(cur)
    return out


def _gray(color: str) -> int:
    """色の明るさ(0 黒〜255 白)。帯の濃さにする"""
    try:
        r, g, b = (int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return 160
    return int(0.299 * r + 0.587 * g + 0.114 * b)


def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() or abs(v) >= 100 else f"{v:.1f}"


# 絵: SVG のうち、線・形・文字だけを描く(色は濃さに。グラデーション・画像・フィルターは描かない)
_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


def _len(v, default: float = 0.0) -> float:
    m = _NUM.match(str(v or "").strip())
    return float(m.group()) if m else default


def _shade(el, key: str, inherited: str | None) -> int | None:
    """fill / stroke の濃さ(0 黒〜255 白)。none なら None"""
    style = dict(kv.split(":", 1) for kv in (el.get("style") or "").replace(" ", "").split(";") if ":" in kv)
    v = style.get(key, el.get(key, inherited))
    if v is None or v == "none" or v == "transparent":
        return None
    v = v.strip().lower()
    named = {"black": 0, "white": 255, "gray": 128, "grey": 128, "currentcolor": 0}
    if v in named:
        return named[v]
    if v.startswith("#") and len(v) == 4:
        v = "#" + "".join(c * 2 for c in v[1:])
    if v.startswith("#") and len(v) == 7:
        return _gray(v)
    m = re.match(r"rgba?\(([^)]*)\)", v)
    if m:
        try:
            r, g, b = (float(x) for x in m.group(1).split(",")[:3])
            return int(0.299 * r + 0.587 * g + 0.114 * b)
        except ValueError:
            return 0
    return 0


def _path_points(d: str) -> list[list[tuple[float, float]]]:
    """path の d を折れ線に(M L H V C Q Z、大文字小文字)"""
    toks = re.findall(r"[MLHVCQZmlhvcqz]|" + _NUM.pattern, d)
    subs: list[list[tuple[float, float]]] = []
    x = y = sx = sy = 0.0
    cmd, i = "M", 0

    def nums(n: int) -> list[float]:
        nonlocal i
        out = [float(t) for t in toks[i:i + n]]
        i += n
        return out
    while i < len(toks):
        if re.fullmatch(r"[A-Za-z]", toks[i]):
            cmd = toks[i]
            i += 1
            if cmd in "Zz":
                if subs:
                    subs[-1].append((sx, sy))
                x, y = sx, sy
                continue
        rel = cmd.islower()
        c = cmd.upper()
        need = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "Q": 4}.get(c, 0)
        if not need or i + need > len(toks) or any(re.fullmatch(r"[A-Za-z]", t) for t in toks[i:i + need]):
            i += 1
            continue
        v = nums(need)
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if c == "M":
            x, y = v[0] + ox, v[1] + oy
            sx, sy = x, y
            subs.append([(x, y)])
            cmd = "l" if rel else "L"
            continue
        if not subs:
            subs.append([(x, y)])
        if c == "L":
            x, y = v[0] + ox, v[1] + oy
        elif c == "H":
            x = v[0] + (x if rel else 0)
        elif c == "V":
            y = v[0] + (y if rel else 0)
        elif c in "CQ":
            pts = [(v[k] + ox, v[k + 1] + oy) for k in range(0, need, 2)]
            p0 = (x, y)
            for s in range(1, 13):
                t = s / 12
                if c == "C":
                    (x1, y1), (x2, y2), (x3, y3) = pts
                    px = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t * t * x2 + t ** 3 * x3
                    py = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t * t * y2 + t ** 3 * y3
                else:
                    (x1, y1), (x2, y2) = pts
                    px = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * x1 + t * t * x2
                    py = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * y1 + t * t * y2
                subs[-1].append((px, py))
            x, y = pts[-1]
            continue
        subs[-1].append((x, y))
    return [s for s in subs if s]


def draw_svg(text: str):
    """SVG(の線・形・文字)を、幅 384 の灰色の絵に。読めなければ ValueError"""
    import xml.etree.ElementTree as ET

    from PIL import Image, ImageDraw
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"絵(SVG)が読めない: {e}") from None
    vb = [_len(v) for v in re.split(r"[ ,]+", (root.get("viewBox") or "").strip()) if v]
    if len(vb) == 4 and vb[2] > 0 and vb[3] > 0:
        ox, oy, vw, vh = vb
    else:
        ox, oy, vw, vh = 0.0, 0.0, _len(root.get("width"), 384) or 384, _len(root.get("height"), 384) or 384
    k = (WIDTH - PAD * 2) / vw
    h = max(1, min(int(vh * k), WIDTH * 2))
    img = Image.new("L", (WIDTH - PAD * 2, h), 255)
    d = ImageDraw.Draw(img)
    P = lambda px, py: ((px - ox) * k, (py - oy) * k)  # noqa: E731

    def walk(el, fill: str | None, stroke: str | None, sw: float) -> None:
        tag = el.tag.split("}")[-1]
        f_in = el.get("fill", fill)
        s_in = el.get("stroke", stroke)
        sw = _len(el.get("stroke-width"), sw)
        fl, st = _shade(el, "fill", f_in), _shade(el, "stroke", s_in)
        w = max(1, int(round(sw * k)))
        if tag == "rect":
            x0, y0 = P(_len(el.get("x")), _len(el.get("y")))
            x1, y1 = P(_len(el.get("x")) + _len(el.get("width")), _len(el.get("y")) + _len(el.get("height")))
            d.rectangle([x0, y0, x1, y1], fill=fl, outline=st, width=w if st is not None else 0)
        elif tag in ("circle", "ellipse"):
            cx, cy = _len(el.get("cx")), _len(el.get("cy"))
            rx = _len(el.get("r") or el.get("rx"))
            ry = _len(el.get("r") or el.get("ry"))
            (x0, y0), (x1, y1) = P(cx - rx, cy - ry), P(cx + rx, cy + ry)
            d.ellipse([x0, y0, x1, y1], fill=fl, outline=st, width=w if st is not None else 0)
        elif tag == "line":
            if st is not None:
                d.line([P(_len(el.get("x1")), _len(el.get("y1"))), P(_len(el.get("x2")), _len(el.get("y2")))], fill=st, width=w)
        elif tag in ("polyline", "polygon", "path"):
            if tag == "path":
                subs = _path_points(el.get("d") or "")
            else:
                vals = [float(v) for v in _NUM.findall(el.get("points") or "")]
                subs = [list(zip(vals[0::2], vals[1::2]))]
            for sub in subs:
                pts = [P(px, py) for px, py in sub]
                closed = tag == "polygon" or (tag == "path" and fl is not None)
                if closed and fl is not None and len(pts) > 2:
                    d.polygon(pts, fill=fl)
                if st is not None and len(pts) > 1:
                    d.line(pts + ([pts[0]] if tag == "polygon" else []), fill=st, width=w, joint="curve")
        elif tag == "text":
            words = "".join(el.itertext()).strip()
            if words:
                size = max(8, int(_len(el.get("font-size"), 16) * k))
                x0, y0 = P(_len(el.get("x")), _len(el.get("y")))
                d.text((x0, y0 - size), words, font=_font(size), fill=fl if fl is not None else 0)
        for ch in el:
            walk(ch, f_in, s_in, sw)
    walk(root, "black", None, 1.0)
    return img


def _graph(d, y: int, vals: list[tuple[float, float]], x_max: float, ticks: list[tuple[float, str]], gh: int = 110,
           log: bool = False, bars: bool = False) -> int:
    """折れ線(か棒)。vals は (x, 値)。返すのは次の y"""
    gx0, gx1 = PAD, WIDTH - PAD
    f_small = _font(16)
    d.line([gx0, y + gh, gx1, y + gh], fill=0, width=1)
    for tx, lab in ticks:
        x = gx0 + (gx1 - gx0) * tx / x_max
        d.line([x, y + gh, x, y + gh + 4], fill=0, width=1)
        d.text((min(max(x - d.textlength(lab, font=f_small) / 2, 0), WIDTH - 20), y + gh + 5), lab, font=f_small, fill=0)
    if vals:
        f = (lambda v: math.log10(max(v, 0) + 1)) if log else (lambda v: v)
        vs = [f(v) for _, v in vals]
        lo, hi = min(vs), max(vs)
        span = (hi - lo) or 1
        X = lambda t: gx0 + (gx1 - gx0) * t / x_max  # noqa: E731
        Y = lambda v: y + gh - 4 - (f(v) - lo) / span * (gh - 10)  # noqa: E731
        if bars:
            bw = max(2, (gx1 - gx0) / max(len(vals), 1) - 2)
            for t, v in vals:
                d.rectangle([X(t), Y(v), X(t) + bw, y + gh], fill=0)
        else:
            segs: list[list[tuple[float, float]]] = [[]]
            prev = None
            for t, v in vals:
                if prev is not None and t - prev > 20:   # 20 分より空いたら線を切る
                    segs.append([])
                segs[-1].append((X(t), Y(v)))
                prev = t
            for seg in segs:
                if len(seg) > 1:
                    d.line(seg, fill=0, width=3)
                elif seg:
                    d.ellipse([seg[0][0] - 2, seg[0][1] - 2, seg[0][0] + 2, seg[0][1] + 2], fill=0)
    return y + gh + 30


def render(slip: dict, base: Path | None = None):
    """紙の絵(PIL の 1 bit 画像)"""
    from PIL import Image, ImageDraw
    w = WIDTH
    ch = character(slip.get("character", ""), base)
    img = Image.new("L", (w, 6000), 255)
    d = ImageDraw.Draw(img)
    y = 6
    d.rectangle([0, y, w - 1, y + 22], fill=_gray(ch["color"]))   # その子の色を灰色の濃さで(ディザで点になる)
    y += 30
    day = Date.fromisoformat(slip["date"])
    f_head, f_small, f_edge = _font(24), _font(16), _font(17)
    d.text((PAD, y), ch["name"], font=f_head, fill=0)
    stamp = f"{day.year}.{day.month}.{day.day}({WEEKDAYS[day.weekday()]})"
    d.text((w - PAD - d.textlength(stamp, font=f_small), y + 6), stamp, font=f_small, fill=0)
    y += 42
    blocks = slip.get("blocks")
    if blocks is None:   # はじめの形(線 1 本 + 一行)
        blocks = ([{"kind": "line", "line": slip["line"], "points": slip.get("points") or []}] if slip.get("line") in LINES else []) + \
                 [{"kind": "text", "text": slip.get("text", "")}]
    for b in blocks:
        if y > 5000:
            break
        if b["kind"] == "text":
            t = b["text"]
            f_text = _font(28 if len(t) <= 40 and "\n" not in t else 22)
            lh = 38 if f_text.size == 28 else 32
            for ln in _wrap(d, t, f_text, w - PAD * 2):
                d.text((PAD, y), ln, font=f_text, fill=0)
                y += lh
            y += 10
        elif b["kind"] == "line" and b.get("line") in LINES:
            name, _, _, unit = LINES[b["line"]]
            pts = b.get("points") or []
            if pts:
                vs = [p[1] for p in pts]
                label = f"{name} {_num(min(vs))}〜{_num(max(vs))}{unit}" + ("(目盛りは対数)" if b["line"] == "amb" else "")
            else:
                label = f"{name}(記録なし)"
            d.text((PAD, y), label, font=f_small, fill=0)
            y = _graph(d, y + 24, [(p[0], p[1]) for p in pts], 1440, [(h * 60, str(h)) for h in (0, 6, 12, 18, 24)], log=b["line"] == "amb")
        elif b["kind"] == "sound":
            vals = b.get("values") or []
            label = f"{b.get('name', '音')} {_num(min(vals))}〜{_num(max(vals))} {b.get('unit', '')}" if vals else b.get("name", "音")
            d.text((PAD, y), label.strip(), font=f_small, fill=0)
            n = max(len(vals), 1)
            ticks = [(0, "0"), (n, f"{n} 秒" if "1 秒" in b.get("unit", "") else f"{n / 10:g} 秒")]
            y = _graph(d, y + 24, list(enumerate(vals)), n, ticks, gh=80, bars=True)
        elif b["kind"] in ("photo", "draw"):
            p = base_dir(base) / b.get("file", "")
            try:
                if b["kind"] == "draw":
                    pic = draw_svg(p.read_text(encoding="utf-8"))
                    img.paste(pic, (PAD, y))
                else:
                    pic = Image.open(p).convert("L")
                    if pic.width != w:
                        pic = pic.resize((w, max(1, int(pic.height * w / pic.width))))
                    img.paste(pic, (0, y))
                y += pic.height + 12
            except (OSError, ValueError):
                d.text((PAD, y), "(写真・絵が読めなかった)", font=f_small, fill=0)
                y += 26
    if slip.get("edge"):
        y += 4
        for ln in _wrap(d, slip["edge"], f_edge, w - PAD * 2):
            d.text((w - PAD - d.textlength(ln, font=f_edge), y), ln, font=f_edge, fill=0)
            y += 24
    y += 10
    return img.crop((0, 0, w, min(y, 6000))).convert("1", dither=Image.Dither.FLOYDSTEINBERG)


# ---- 刷る(ESC/POS ラスタ、Bluetooth RFCOMM)----

def printer_address(base: Path | None = None) -> str:
    addr = os.environ.get("PRINTER_ADDRESS", "")
    if addr:
        return addr.strip()
    try:
        for ln in (base_dir(base) / ".env").read_text(encoding="utf-8").splitlines():
            if ln.startswith("PRINTER_ADDRESS="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def packet(img) -> bytes:
    wb = WIDTH // 8
    h = img.height
    px = img.load()
    rows = bytearray()
    for yy in range(h):
        row = bytearray(wb)
        for xx in range(WIDTH):
            if px[xx, yy] == 0:
                row[xx // 8] |= 0x80 >> (xx % 8)
        rows += row
    return b"\x1b\x40" + bytes([0x1D, 0x76, 0x30, 0x00, wb & 0xFF, wb >> 8, h & 0xFF, h >> 8]) + bytes(rows) + b"\n" * 6


def send(addr: str, data: bytes, channel: int = 1) -> None:
    s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    s.settimeout(15)
    try:
        s.connect((addr, channel))
        for i in range(0, len(data), 512):
            s.send(data[i:i + 512])
    finally:
        s.close()


def print_slips(ids: list[str], base: Path | None = None) -> dict:
    """紙を順に刷る。1 枚ずつ切れるように間をあける。結果: {"done": [...], "error": "..."}"""
    addr = printer_address(base)
    if not addr:
        return {"done": [], "error": "プリンターの住所(PRINTER_ADDRESS)が家の .env にありません"}
    lock = base_dir(base) / "state" / "printer.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    done: list[str] = []
    with open(lock, "w") as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return {"done": [], "error": "プリンターを、ほかで使っているところです。少し待ってから"}
        for sid in ids:
            slip = find(sid, base)
            if not slip:
                continue
            try:
                send(addr, packet(render(slip, base)), int(os.environ.get("PRINTER_CHANNEL", "1")))
            except OSError as e:
                return {"done": done, "error": f"プリンターにつながりませんでした(電源と紙を確かめてね): {e.__class__.__name__}"}
            mark(sid, "printed_at", base)
            done.append(sid)
    return {"done": done, "error": ""}


def describe(slip: dict) -> str:
    day = Date.fromisoformat(slip["date"])
    sm = summary(slip)
    state = "刷った" if slip.get("printed_at") else ("しまった" if slip.get("put_away") else "まだ刷っていない")
    return f"{day.month}/{day.day}({WEEKDAYS[day.weekday()]}) {slip['character']}: {sm['kinds']}「{sm['text']}」({state})  [id {slip['id']}]"


class _Part(argparse.Action):
    """--text / --line / --photo / --drawing / --draw / --sound を、書いた順のまま parts に"""
    def __call__(self, parser, ns, value, option_string=None):
        ns.parts = (getattr(ns, "parts", None) or []) + [(self.dest, value)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="合作日記の紙")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("line")
    p.add_argument("--character", required=True)
    p = sub.add_parser("make")
    p.add_argument("--character", required=True)
    for k in ("text", "line", "photo", "drawing", "draw", "sound"):
        p.add_argument(f"--{k}", dest=k, action=_Part)
    p.add_argument("--edge", default="")
    p.add_argument("words", nargs="?", help="--text と同じ(はじめの形)")
    p.set_defaults(parts=None)
    p = sub.add_parser("list")
    p.add_argument("--character")
    p.add_argument("--all", action="store_true")
    p = sub.add_parser("preview")
    p.add_argument("id")
    p.add_argument("out")
    a = ap.parse_args(argv)
    if a.cmd == "line":
        s = line(a.character)
        if s:
            print(s)
        return 0
    if a.cmd == "make":
        parts = list(a.parts or []) + ([("text", a.words)] if a.words else [])
        ok, msg = make(a.character, parts, a.edge)
        print(msg)
        return 0 if ok else 1
    if a.cmd == "list":
        items = [x for x in load() if (not a.character or x.get("character") == a.character)
                 and (a.all or not (x.get("printed_at") or x.get("put_away")))]
        print("\n".join(describe(x) for x in items) if items else "紙はありません")
        return 0
    slip = find(a.id)
    if not slip:
        print("その紙はありません", file=sys.stderr)
        return 1
    render(slip).save(a.out)
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
