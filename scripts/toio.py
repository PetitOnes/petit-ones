#!/usr/bin/env python3
"""🧊 toio: 小さいキューブを、マットの上で動かす(2026-11-18)。

キューブとつながっているのは番人(scripts/toio_server.py)だけ。この道具は番人に頼んで、
走ったあとの「数字と線」(通った点・ぶつかった・傾いた・マットの外で場所を失った)を返す。

    python3 toio.py status                              # キューブの今(だれの分・つながり・電池・場所)
    python3 toio.py move <id> <x> <y> [--speed 50]      # その場所へ行く
    python3 toio.py path <id> '[[x,y], [x,y], …]' [--speed 50]   # 順に通る(20 点まで)
    python3 toio.py drive <id> <左> <右> <ミリ秒>        # 左右の車輪の速さ(-115〜115)で走る(3 秒まで)。マットの端を確かめるときに
    python3 toio.py light <id> <#rrggbb>                # ランプの色("" で消す)
    python3 toio.py last <id> [--n 1] [--by <だれ>]      # 走ったあとの数字と線をもう一度
    python3 toio.py map                                 # みんなのキューブがマットのどこにいるか

場所はマットの目盛り(簡易プレイマットなら x 98〜402・y 142〜358、左上が小さい)。向きは 0〜359 度(右が 0、時計回り)。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

MAX_DRIVE_MS = 3000
MAX_POINTS = 20
OFF_MAT_MARGIN = 40   # マットの外へ、これだけははみ出した目標を許す(端を確かめるため)
DEFAULT_MAT = {"name": "簡易プレイマット", "x0": 98, "x1": 402, "y0": 142, "y1": 358}
MOVE_RESULT = {0: "着いた", 1: "時間切れ(着かなかった)", 2: "マットの外で場所を失った", 3: "頼み方がおかしい",
               4: "電源が切れた", 5: "次の頼みで上書きされた", 6: "このキューブでは使えない"}
EVENT = {"lost": "場所を失った", "found": "マットに戻った", "bump": "ぶつかった", "tilt": "傾いた", "start_off_mat": "マットの外から走りはじめた"}


class ToioError(Exception):
    pass


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR", Path.home() / "petit_claude"))


def petits(base: Path) -> list[str]:
    """家の子(characters/<id>/config/config.json がある子)"""
    root = base / "characters"
    return sorted(d.name for d in root.iterdir() if (d / "config" / "config.json").is_file()) if root.is_dir() else []


def color_of(base: Path, who: str) -> str:
    try:
        return json.loads((base / "characters" / who / "config" / "config.json").read_text(encoding="utf-8")).get("color") or "#ffffff"
    except (OSError, json.JSONDecodeError):
        return "#ffffff"


def rgb(color: str) -> tuple[int, int, int]:
    c = color.strip().lstrip("#")
    if len(c) != 6:
        raise ToioError("色は #rrggbb で(たとえば #00afcc)")
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError as e:
        raise ToioError("色は #rrggbb で(たとえば #00afcc)") from e


def led(color: str) -> tuple[int, int, int]:
    """ランプ用の色。淡い色(ラベンダーなど)は白に見えてしまうので、色味を強めて明るさをいっぱいに"""
    import colorsys
    r, g, b = rgb(color)
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if s < 0.05:
        return r, g, b   # 白・灰色はそのまま
    r2, g2, b2 = colorsys.hsv_to_rgb(h, max(s, 0.75), 1.0)
    return round(r2 * 255), round(g2 * 255), round(b2 * 255)


def load_config(base: Path) -> dict:
    try:
        return json.loads((base / "config" / "toio.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def enabled(base: Path) -> bool:
    """家で toio を使うか(⚙️ 設定 → 家 → 🧊 toio)。決めていなければ使う"""
    return load_config(base).get("on", True) is not False


def set_enabled(base: Path, on: bool) -> dict:
    cfg = load_config(base)
    cfg["on"] = bool(on)
    p = base / "config" / "toio.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    return cfg


def mat_of(cfg: dict) -> dict:
    return {**DEFAULT_MAT, **(cfg.get("mat") or {})}


def clamp_speed(v: object) -> int:
    """目標へ行く速さ(10〜115)"""
    return max(10, min(115, int(v)))


def clamp_wheel(v: object) -> int:
    """車輪の速さ(-115〜115)。8 より小さいと動かないので 0 に"""
    n = max(-115, min(115, int(v)))
    return 0 if abs(n) < 8 else n


def check_point(cfg: dict, x: object, y: object) -> tuple[int, int]:
    m = mat_of(cfg)
    x, y = int(x), int(y)
    if not (m["x0"] - OFF_MAT_MARGIN <= x <= m["x1"] + OFF_MAT_MARGIN and m["y0"] - OFF_MAT_MARGIN <= y <= m["y1"] + OFF_MAT_MARGIN):
        raise ToioError(f"マット({m['name']})は x {m['x0']}〜{m['x1']}・y {m['y0']}〜{m['y1']}。外へは {OFF_MAT_MARGIN} までしか行けません")
    return x, y


def check_path(cfg: dict, points: object) -> list[tuple[int, int]]:
    if not isinstance(points, list) or not points:
        raise ToioError("通る点は [[x,y], [x,y], …] で")
    if len(points) > MAX_POINTS:
        raise ToioError(f"通る点は {MAX_POINTS} までです")
    try:
        return [check_point(cfg, p[0], p[1]) for p in points]
    except (TypeError, IndexError, ValueError) as e:
        raise ToioError("通る点は [[x,y], [x,y], …] で") from e


def thin(trail: list[list[float]], step: float = 2.0, most: int = 600) -> list[list[float]]:
    """ほとんど動いていない点を落とす。多すぎたら間引く"""
    out: list[list[float]] = []
    for p in trail:
        if not out or abs(p[1] - out[-1][1]) + abs(p[2] - out[-1][2]) >= step or p is trail[-1]:
            out.append(p)
    if len(out) > most:
        k = len(out) / most
        out = [out[int(i * k)] for i in range(most - 1)] + [out[-1]]
    return out


# ---- 残す・読む ----

def _runs_path(base: Path) -> Path:
    return base / "state" / "toio" / "runs.jsonl"


def save_run(base: Path, run: dict) -> None:
    p = _runs_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")


def runs(base: Path, who: str | None = None, by: str | None = None, n: int = 1) -> list[dict]:
    try:
        rows = [json.loads(x) for x in _runs_path(base).read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, json.JSONDecodeError):
        return []
    rows = [r for r in rows if (not who or r.get("who") == who) and (not by or r.get("by") == by)]
    return rows[-n:]


# ---- 数字と線 ----

def ascii_map(mat: dict, trail: list, events: list | None = None, others: dict | None = None, w: int = 38) -> str:
    """マットを文字の升目に。· 通った所、S はじめ、E おわり、× 場所を失った所、! ぶつかった所、ほかの子は頭文字"""
    sx, sy = mat["x1"] - mat["x0"], mat["y1"] - mat["y0"]
    h = max(6, round(w * sy / sx / 2))   # 文字は縦に長いので半分

    def cell(x: float, y: float) -> tuple[int, int] | None:
        c, r = int((x - mat["x0"]) / sx * w), int((y - mat["y0"]) / sy * h)
        return (min(w - 1, max(0, c)), min(h - 1, max(0, r))) if -2 <= c <= w + 1 and -2 <= r <= h + 1 else None

    grid = [[" "] * w for _ in range(h)]

    def put(x: float, y: float, ch: str) -> None:
        if (rc := cell(x, y)) is not None:
            grid[rc[1]][rc[0]] = ch
    for p in trail:
        put(p[1], p[2], "·")
    for name, pos in (others or {}).items():
        put(pos["x"], pos["y"], name[:1])
    if trail:
        put(trail[0][1], trail[0][2], "S")
        put(trail[-1][1], trail[-1][2], "E")
    for e in events or []:
        if "x" in e:
            put(e["x"], e["y"], {"lost": "×", "found": "○"}.get(e["kind"], "!"))
    return "\n".join(["┌" + "─" * w + "┐"] + ["│" + "".join(r) + "│" for r in grid] + ["└" + "─" * w + "┘"])


def marks_of(ids: list[str]) -> dict[str, str]:
    """地図の印: 名前の、みんなと同じはじまりを除いた 1 文字目(puchiko → k)。重なれば数字"""
    pre = os.path.commonprefix(ids) if len(ids) > 1 else ""
    out: dict[str, str] = {}
    for i, w in enumerate(ids):
        m = (w[len(pre):] or w)[:1]
        out[w] = m if m not in out.values() else str(i + 1)
    return out


def summarize(run: dict, mat: dict) -> str:
    tr, ev = run.get("trail") or [], run.get("events") or []
    rows = [f"{run.get('at', '').replace('T', ' ')}  {run.get('who')} のキューブ({'自分で' if run.get('by') == run.get('who') else run.get('by', '') + ' が'}動かした): {run.get('result')}、{run.get('seconds')} 秒"]
    if tr:
        dist = sum(((b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2) ** 0.5 for a, b in zip(tr, tr[1:]))
        rows.append(f"はじめ ({tr[0][1]}, {tr[0][2]}) 向き {tr[0][3]}° → おわり ({tr[-1][1]}, {tr[-1][2]}) 向き {tr[-1][3]}°、通った長さ {round(dist)}(目盛り)、点 {len(tr)} 個")
        xs, ys = [p[1] for p in tr], [p[2] for p in tr]
        rows.append(f"通った範囲 x {min(xs)}〜{max(xs)}・y {min(ys)}〜{max(ys)}(マットは x {mat['x0']}〜{mat['x1']}・y {mat['y0']}〜{mat['y1']})")
    else:
        rows.append("場所は一度も読めませんでした(マットの上にいない?)")
    for e in ev:
        where = f" ({e['x']}, {e['y']})" if "x" in e else ""
        rows.append(f"  {e.get('t')} 秒: {EVENT.get(e.get('kind'), e.get('kind'))}{where}{'・' + e['posture'] if e.get('posture') else ''}")
    rows.append(ascii_map(mat, tr, ev))
    return "\n".join(rows)


# ---- 番人に頼む ----

def _url() -> str:
    return os.environ.get("PETIT_TOIO_URL", f"http://127.0.0.1:{os.environ.get('PETIT_TOIO_PORT', '8774')}")


def ask(path: str, body: dict | None = None, timeout: float = 120) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(_url() + path, data=data, headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            raise ToioError(json.loads(e.read().decode()).get("error", "うまくいきませんでした")) from e
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ToioError("うまくいきませんでした") from e
    except (urllib.error.URLError, OSError) as e:
        raise ToioError("toio の番人(toio_server.py)が動いていません") from e


def status_text(st: dict) -> str:
    m = st.get("mat") or DEFAULT_MAT
    rows = [f"マット: {m['name']}(x {m['x0']}〜{m['x1']}・y {m['y0']}〜{m['y1']})"]
    for c in st.get("cubes", []):
        if not c.get("connected"):
            rows.append(f"- {c.get('who') or '(だれの分でもない)'}: つながっていない")
            continue
        p = c.get("pos")
        where = f"({p['x']}, {p['y']}) 向き {p['a']}°" if p else "マットの外" + (f"(最後に読めたのは {c['last_pos']['x']}, {c['last_pos']['y']})" if c.get("last_pos") else "")
        rows.append(f"- {c.get('who') or '(だれの分でもない)'}: {where}、{c.get('posture')}、電池 {c.get('battery')}%{'、動いている最中' if c.get('busy') else ''}")
    return "\n".join(rows) if st.get("cubes") else "キューブがつながっていません(電源を入れて、ダッシュボードの 🧊 で「探す」)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="toio: 小さいキューブを動かす")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("map")
    sub.add_parser("scan")
    sub.add_parser("enabled")
    p = sub.add_parser("move")
    p.add_argument("who")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("--speed", type=int, default=50)
    p = sub.add_parser("path")
    p.add_argument("who")
    p.add_argument("points")
    p.add_argument("--speed", type=int, default=50)
    p = sub.add_parser("drive")
    p.add_argument("who")
    p.add_argument("left", type=int)
    p.add_argument("right", type=int)
    p.add_argument("ms", type=int)
    p = sub.add_parser("light")
    p.add_argument("who")
    p.add_argument("color")
    p = sub.add_parser("last")
    p.add_argument("who")
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--by")
    a = ap.parse_args(argv)
    base = data_dir()
    mat = mat_of(load_config(base))
    if a.cmd == "enabled":   # 自律行動がプロンプトに toio の行を入れるか決める(使うなら 1)
        print("1" if enabled(base) else "")
        return 0
    try:
        if a.cmd not in ("status", "last") and not enabled(base):
            raise ToioError("toio は、いま家で使わないことになっています(⚙️ 設定で決める)")
        if a.cmd == "status":
            print(status_text(ask("/cubes")))
        elif a.cmd == "scan":
            print(status_text(ask("/scan", {}, 90)))
        elif a.cmd == "map":
            st = ask("/cubes")
            here = {c["who"]: c["pos"] for c in st.get("cubes", []) if c.get("who") and c.get("pos")}
            marks = marks_of(list(here))
            print(ascii_map(mat, [], others={marks[w]: pos for w, pos in here.items()}))
            print("(" + "・".join(f"{m} = {w}" for w, m in marks.items()) + "。マットの外にいる子は出ません)" if here else "(マットの上にいる子はいません)")
        elif a.cmd == "move":
            print(summarize(ask("/move", {"who": a.who, "by": a.who, "x": a.x, "y": a.y, "speed": a.speed}), mat))
        elif a.cmd == "path":
            try:
                pts = json.loads(a.points)
            except json.JSONDecodeError as e:
                raise ToioError(f"通る点の JSON が読めません: {e}") from e
            check_path(load_config(base), pts)
            print(summarize(ask("/path", {"who": a.who, "by": a.who, "points": pts, "speed": a.speed}, 300), mat))
        elif a.cmd == "drive":
            print(summarize(ask("/drive", {"who": a.who, "by": a.who, "left": a.left, "right": a.right, "ms": a.ms}), mat))
        elif a.cmd == "light":
            if a.color:
                rgb(a.color)
            ask("/light", {"who": a.who, "color": a.color})
            print("ランプを変えました" if a.color else "ランプを消しました")
        elif a.cmd == "last":
            rows = runs(base, a.who, a.by, a.n)
            print("\n\n".join(summarize(r, mat) for r in rows) if rows else "まだ走っていません")
    except ToioError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
