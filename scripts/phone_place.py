#!/usr/bin/env python3
"""スマホの居場所: 家の印(SwitchBot の機体が出している BLE)をスマホが聞いて、どの部屋にいるかを決める。

SwitchBot の機体(ハブ 2・温湿度計・人感・電気)は、機体 ID そのままの MAC で BLE をずっと出している。
部屋ごとにどの機体があるかは config/spots.json(家の中の場所)に書いてある。
スマホ(Android の Garmin BLE Bridge アプリ)が 30 秒ごとに、見えた機体と電波の強さ(RSSI)を
ダッシュボードの POST /api/beacons/report に送ってくる。ここはそれを部屋に直して覚える(2026-11-14 ありさん)。

設定 PETIT_DATA_DIR/config/beacons.json(無ければ何もしない):

    {"phones": {"arisan": {"key": "<長いランダムな文字列>", "label": "ありさんのスマホ"}},
     "hysteresis_db": 6, "fresh_s": 240, "window": 3, "min_rssi": -95}

- phones: ダッシュボードのユーザー名ごとに、スマホが名乗る鍵(X-Petit-Key)。鍵は `phone_place.py key <ユーザー名>` で作る
- hysteresis_db: いまの部屋より、これだけ強い部屋が出たときだけ移る(部屋の境目でパタパタしないように)
- fresh_s: 最後の報告がこれより古ければ「分からない」
- window: 直近いくつの報告のまんなか(中央値)で決めるか
- min_rssi: これより弱い電波は「見えていない」と同じ

覚え書き PETIT_DATA_DIR/state/phone_place.json:

    {"arisan": {"room": "あり部屋", "since": "...", "at": "...", "levels": {"あり部屋": -58, "寝室": -81},
                "history": [{"at": "...", "rooms": {"あり部屋": -60}}]}}

- room: いまいる部屋(どの印も見えなければ null)。since はその部屋になった時刻、at は最後の報告
- 部屋は分かるが、ソファか机かまでは電波では分からない
- net: 家のネットワークにいるか({"home": true/false, "at": "..."})。スマホの報告が PC にどう届いたかで見る(下)

家の印が見えないとき、お外なのか、印の無い部屋なのか(2026-11-16 ありさん「スマホの Wi-Fi が家じゃないときに、外だよってわかるように」):
スマホの報告は Tailscale を通って PC に届く。そのとき PC から見たスマホの実際のアドレス(tailscale status の CurAddr)が、
PC と同じネットワーク(家の Wi-Fi)なら「家にいる」、ちがう(ほかのスマホのテザリング・出先の Wi-Fi・モバイル回線)なら「家の Wi-Fi にいない」。
中継(DERP)ごしで実際のアドレスが分からないときは、どちらとも言わない。アプリは変えなくてよい。

- 印が見える                          → 家(部屋)。家でモバイル回線のままでも、印が見えていれば家
- 印が見えない + 家の Wi-Fi にいる     → 家(印の無い部屋)
- 印が見えない + 家の Wi-Fi にいない   → お外
- 印が見えない + 分からない            → 家の印が見えない(お外か、印の無い部屋)

ぷちには毎回は渡さない(2026-11-14 ありさん「伝わるってより、見に行けば分かる、にしたい」)。
「見に行けるもの」の入口に `phone_place.py line` を置き、部屋が変わった・帰ってきた・出たときだけ 1 行(changes --mark):

    line:     ありさんのスマホ: 家(あり部屋)
              ありさんのスマホ: 家(印の無い部屋。家の Wi-Fi にいる)
              ありさんのスマホ: お外(家の印も、家の Wi-Fi も見えない)
              ありさんのスマホ: 家の印が見えない(お外か、印の無い部屋)
    changes:  ありさんのスマホ: あり部屋 → 寝室 に動いた
              ありさんのスマホ: 家(あり部屋)に戻ってきた
              ありさんのスマホ: お外に出た(家の印も、家の Wi-Fi も見えなくなった)
              ありさんのスマホ: 家の印が見えなくなった(お外に出たか、印の無い部屋)

伝えたことは characters/<id>/state/phone_told.json に覚える(はじめての回は覚えるだけで何も言わない)。

Usage:
    python3 phone_place.py key <ユーザー名> [--label "ありさんのスマホ"]   # 鍵を作って設定に書く(鍵は画面に出さない)
    python3 phone_place.py show                                          # いまの覚え書き
    python3 phone_place.py line                                          # 見に行ったときの行
    python3 phone_place.py changes --character <id> [--mark]             # その子に前に伝えてから変わったときだけの行
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULTS = {"hysteresis_db": 6, "fresh_s": 240, "window": 3, "min_rssi": -95}
SILENT = -100          # 見えていない部屋の電波の強さ、として扱う値
INTERVAL_S = 30        # スマホが報告する間隔(アプリに伝える)
HISTORY_MAX = 10
OUT, HOME = "@out", "@home"   # 伝えた覚え(phone_told.json)での「お外」「家(印の無い部屋)」。部屋の名前とぶつからない形
TAILNET = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))
SKIP_IF = ("lo", "tailscale", "docker", "br-", "veth", "virbr")   # 家のネットワークではないインターフェース


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def config_path(base: Path | None = None) -> Path:
    return (base or data_dir()) / "config" / "beacons.json"


def state_path(base: Path | None = None) -> Path:
    return (base or data_dir()) / "state" / "phone_place.json"


def config(base: Path | None = None) -> dict:
    try:
        raw = json.loads(config_path(base).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    out = {**DEFAULTS, **{k: v for k, v in raw.items() if k in DEFAULTS and isinstance(v, (int, float))}}
    phones = raw.get("phones") if isinstance(raw.get("phones"), dict) else {}
    out["phones"] = {u: p for u, p in phones.items() if isinstance(p, dict) and p.get("key")}
    return out


def person_for_key(key: str | None, base: Path | None = None) -> str | None:
    """名乗った鍵がだれのスマホか。合わなければ None"""
    if not key:
        return None
    for user, p in config(base)["phones"].items():
        if secrets.compare_digest(str(p["key"]), key):
            return user
    return None


def make_key(user: str, label: str = "", base: Path | None = None) -> None:
    """鍵を作って設定に書く(前の鍵は捨てる)。鍵そのものは返さない"""
    p = config_path(base)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    phones = raw.setdefault("phones", {})
    phones[user] = {"key": secrets.token_urlsafe(32), "label": label or phones.get(user, {}).get("label") or f"{user} のスマホ"}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass


def norm_mac(mac: str) -> str:
    return "".join(c for c in str(mac).upper() if c in "0123456789ABCDEF")


def mac_rooms(base: Path | None = None) -> dict[str, str]:
    """印(機体の MAC)→ 部屋。家の中の場所(spots.json)から"""
    import spots
    out: dict[str, str] = {}
    for s in spots.load(base):
        for d in s.get("devices") or []:
            out.setdefault(norm_mac(d), s["room"])
    return out


def macs(base: Path | None = None) -> list[str]:
    """スマホに「これを聞いて」と渡す MAC の一覧(12 桁、大文字)"""
    return sorted(mac_rooms(base))


def rooms_from_seen(seen: dict, base: Path | None = None, min_rssi: float = DEFAULTS["min_rssi"]) -> dict[str, int]:
    """見えた機体と強さ → 部屋ごとのいちばん強い値"""
    rooms = mac_rooms(base)
    out: dict[str, int] = {}
    for mac, rssi in (seen or {}).items():
        room = rooms.get(norm_mac(mac))
        try:
            v = int(rssi)
        except (TypeError, ValueError):
            continue
        if room and v >= min_rssi:
            out[room] = max(out.get(room, SILENT), v)
    return out


def _load(base: Path | None) -> dict:
    try:
        d = json.loads(state_path(base).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(base: Path | None, d: dict) -> None:
    p = state_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)


def _median_levels(history: list[dict]) -> dict[str, int]:
    names = {r for h in history for r in (h.get("rooms") or {})}
    out = {}
    for n in names:
        vals = sorted((h.get("rooms") or {}).get(n, SILENT) for h in history)
        out[n] = vals[len(vals) // 2]
    return out


def decide(cur_room: str | None, levels: dict[str, int], hysteresis_db: float) -> str | None:
    """いまの部屋と、部屋ごとの強さから、次の部屋。見える部屋が無ければ None"""
    levels = {r: v for r, v in levels.items() if v > SILENT}   # まんなかが「見えていない」の部屋は候補にしない(引き分けで決めてしまわない)
    if not levels:
        return None
    best = max(levels, key=lambda r: levels[r])
    if cur_room and cur_room in levels and best != cur_room and levels[best] - levels[cur_room] < hysteresis_db:
        return cur_room   # いまの部屋とほとんど差が無いなら、動かない
    return best


def local_nets(addrs: list) -> list:
    """`ip -j addr` の結果 → この PC がいるネットワーク(家の Wi-Fi / 有線)の一覧"""
    out = []
    for i in addrs or []:
        if str(i.get("ifname", "")).startswith(SKIP_IF):
            continue
        for a in i.get("addr_info") or []:
            if a.get("scope") != "global":
                continue
            try:
                out.append(ipaddress.ip_interface(f"{a['local']}/{a['prefixlen']}").network)
            except (KeyError, ValueError):
                continue
    return out


def _ip(text: object):
    """"192.168.1.5:41641" / "[2400:…]:40321" / "192.168.1.5" → アドレス。読めなければ None"""
    t = str(text or "").strip()
    if t.startswith("["):
        t = t[1:].split("]")[0]
    elif t.count(":") == 1:
        t = t.split(":")[0]
    try:
        return ipaddress.ip_address(t)
    except ValueError:
        return None


def on_home_net(client_host: object, status: dict, nets: list) -> bool | None:
    """報告を送ってきた相手が、PC と同じネットワークにいるか。True / False / 分からない(None)

    client_host は報告の送り元。家の中のアドレスならそのまま True。Tailscale のアドレスなら、
    tailscale status(status)でその相手の実際のアドレス(CurAddr)を見る。中継ごしで空なら None
    """
    def inside(ip) -> bool:
        return any(ip.version == n.version and ip in n for n in nets)

    ip = _ip(client_host)
    if ip is None or not nets:
        return None
    if inside(ip):
        return True
    if not any(ip.version == n.version and ip in n for n in TAILNET):
        return None   # 自分自身(プロキシごし)など。見分けられない
    for peer in ((status or {}).get("Peer") or {}).values():
        if any(_ip(a) == ip for a in peer.get("TailscaleIPs") or []):
            cur = _ip(peer.get("CurAddr"))
            return None if cur is None else inside(cur)
    return None


_cache: dict = {}


def _run_json(key: str, cmd: list[str], ttl: float):
    """コマンドの JSON 出力。ttl 秒は覚えておく。動かなければ None"""
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    try:
        val = json.loads(subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=True).stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        val = None
    _cache[key] = (time.monotonic(), val)
    return val


def home_net(client_host: object) -> bool | None:
    """いまの報告の送り元が、家のネットワークにいるか(PC の ip と tailscale に聞く)"""
    nets = local_nets(_run_json("addr", ["ip", "-j", "addr"], 300) or [])
    if not nets:
        return None
    return on_home_net(client_host, _run_json("ts", ["tailscale", "status", "--json"], 20) or {}, nets)


def report(user: str, seen: dict, base: Path | None = None, now: datetime | None = None, home: bool | None = None) -> dict:
    """スマホからの 1 回の報告を取り込み、その人の覚え書きを返す。home は「家のネットワークにいるか」(分からなければ None)"""
    now = now or datetime.now()
    cfg = config(base)
    stamp = now.replace(microsecond=0).isoformat()
    d = _load(base)
    cur = d.get(user) if isinstance(d.get(user), dict) else {}
    history = [h for h in (cur.get("history") or []) if isinstance(h, dict)]
    # 古い報告(fresh_s より前)は、まんなかを取る相手にしない(帰ってきた直後に、出かける前の部屋が残らないように)
    history = [h for h in history if _dt(h.get("at")) and now - _dt(h.get("at")) <= timedelta(seconds=cfg["fresh_s"])]
    history.append({"at": stamp, "rooms": rooms_from_seen(seen, base, cfg["min_rssi"])})
    history = history[-HISTORY_MAX:]
    levels = _median_levels(history[-int(cfg["window"]):])
    room = decide(cur.get("room"), levels, cfg["hysteresis_db"])
    since = cur.get("since") if room == cur.get("room") and cur.get("since") else stamp
    d[user] = {"room": room, "since": since, "at": stamp, "levels": levels, "history": history}
    net = {"home": bool(home), "at": stamp} if home is not None else cur.get("net")   # 分からない回は、前のを持ち越す(古くなれば使わない)
    if isinstance(net, dict):
        d[user]["net"] = net
    _save(base, d)
    return d[user]


def _dt(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def where(user: str, base: Path | None = None, now: datetime | None = None) -> dict | None:
    """その人のスマホの居場所 {"room", "since", "at", "label", "home"}。報告が古い・無いなら None。

    home は家のネットワークにいるか(True / False)。分からない・古いなら None
    """
    now = now or datetime.now()
    cur = _load(base).get(user)
    at = _dt(cur.get("at")) if isinstance(cur, dict) else None
    fresh = timedelta(seconds=config(base)["fresh_s"])
    if at is None or now - at > fresh:
        return None
    label = (config(base)["phones"].get(user) or {}).get("label") or f"{user} のスマホ"
    net = cur.get("net") if isinstance(cur.get("net"), dict) else {}
    net_at = _dt(net.get("at"))
    home = bool(net.get("home")) if net_at and now - net_at <= fresh else None
    return {"room": cur.get("room"), "since": cur.get("since") or "", "at": cur.get("at"), "label": label, "home": home}


def _people_label(base: Path | None = None):
    """ユーザー名 → 呼び名(config/people.json)。無ければそのまま"""
    try:
        people = json.loads(((base or data_dir()) / "config" / "people.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        people = {}
    return lambda u: (people.get(u) or {}).get("name") or u


def words(w: dict) -> str:
    if w.get("room"):
        return f"家({w['room']})"
    if w.get("home") is True:
        return "家(印の無い部屋。家の Wi-Fi にいる)"
    if w.get("home") is False:
        return "お外(家の印も、家の Wi-Fi も見えない)"
    return "家の印が見えない(お外か、印の無い部屋)"


def _told_key(w: dict) -> str | None:
    """伝えた覚えに書く形: 部屋の名前 / OUT / HOME / 分からない(None)"""
    if w.get("room"):
        return w["room"]
    return {True: HOME, False: OUT}.get(w.get("home"))


def _moved(name: str, old: str | None, new: str | None) -> str:
    """前に伝えた居場所 old から new に変わったときの 1 行。言うほどでなければ ""

    「分からない」と「お外」「印の無い部屋」のあいだは、見分けがついた・つかなくなっただけなので言わない
    """
    old_room = old if old not in (None, OUT, HOME) else None
    if new not in (None, OUT, HOME):
        if old_room:
            return f"{name}: {old_room} → {new} に動いた"
        return f"{name}: {new} に動いた" if old == HOME else f"{name}: 家({new})に戻ってきた"
    if new == OUT:
        return f"{name}: お外に出た(家の印も、家の Wi-Fi も見えなくなった)" if old_room or old == HOME else ""
    if new == HOME:
        if old_room:
            return f"{name}: {old_room} から、印の無い部屋に動いた"
        return f"{name}: 家に戻ってきた(印の無い部屋)" if old == OUT else ""
    return f"{name}: 家の印が見えなくなった(お外に出たか、印の無い部屋)" if old_room else ""


def lines(base: Path | None = None, label=lambda u: u, now: datetime | None = None) -> list[str]:
    """ぷちに渡す行。「ありさんのスマホ: 家(あり部屋)」"""
    out = []
    for user in config(base)["phones"]:
        w = where(user, base, now)
        if w:
            out.append(f"{label(user)}のスマホ: {words(w)}")
    return out


def change_line(base: Path | None, character_id: str, mark: bool = False, now: datetime | None = None) -> str:
    """その子に前に伝えた居場所から変わった人だけ 1 行。報告が古い人は分からないので触らない。はじめての回は覚えるだけ"""
    now = now or datetime.now()
    told_path = (base or data_dir()) / "characters" / character_id / "state" / "phone_told.json"
    try:
        told = json.loads(told_path.read_text(encoding="utf-8"))
        first = not isinstance(told, dict)
    except (OSError, json.JSONDecodeError):
        told, first = {}, True
    if first:
        told = {}
    phones = config(base)["phones"]
    lines_out = []
    for user, p in phones.items():
        w = where(user, base, now)
        if w is None:
            continue
        name = (p.get("label") or f"{user} のスマホ")
        new = _told_key(w)
        old = told.get(user)
        if new is None and old in (OUT, HOME):
            continue   # 見分けがつかなくなっただけ。前に伝えたまま(あとで「帰ってきた」を言えるように)
        if not first and user in told and old != new:
            line = _moved(name, old, new)
            if line:
                lines_out.append(line)
        told[user] = new
    if mark:
        told_path.parent.mkdir(parents=True, exist_ok=True)
        told_path.write_text(json.dumps(told, ensure_ascii=False), encoding="utf-8")
    if not _wants_phone(character_id, base):   # 受け取らない子(settings.json の notices.phone)。覚えだけ進めて、何も言わない
        return ""
    return "\n".join(lines_out)


def _wants_phone(character_id: str, base: Path | None) -> bool:
    try:
        import notices
        return notices.wants(character_id, "phone", base)
    except Exception:
        return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("key", help="鍵を作って設定に書く")
    k.add_argument("user")
    k.add_argument("--label", default="")
    sub.add_parser("show")
    sub.add_parser("line")
    c = sub.add_parser("changes", help="その子に前に伝えてから変わったときだけの行")
    c.add_argument("--character", required=True)
    c.add_argument("--mark", action="store_true", help="伝えたことにして覚える")
    a = ap.parse_args()
    if a.cmd == "key":
        make_key(a.user, a.label)
        print(f"{a.user} の鍵を {config_path()} に書いた(鍵は表示しない)")
    elif a.cmd == "show":
        print(json.dumps(_load(None), ensure_ascii=False, indent=1))
    elif a.cmd == "changes":
        out = change_line(None, a.character, mark=a.mark)
        if out:
            print(out)
    else:
        print("\n".join(lines(label=_people_label())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
