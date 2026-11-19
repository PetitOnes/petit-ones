#!/usr/bin/env python3
"""toio の番人(2026-11-18): PC の Bluetooth で toio コア キューブとつながったままにして、HTTP で頼まれたことをする。

ぷち(scripts/toio.py)も、ダッシュボードのコントローラも、ここに頼む。toio は同時に 1 台にしかつながらないので、
つなぐのはこの番人だけにする。

    python3 scripts/toio_server.py            # 127.0.0.1:8774 で待つ(PETIT_TOIO_PORT で変えられる)

家の値(キューブとだれの分か、マットの範囲)は PETIT_DATA_DIR/config/toio.json(git に入れない)。
走ったあとの記録は PETIT_DATA_DIR/state/toio/runs.jsonl(1 回 1 行: だれの・だれが動かした・通った点・出来事)。

HTTP:
    GET  /cubes                        キューブの今(つながり・電池・場所・向き・傾き)
    POST /scan                         探して、見つけた分につなぐ。だれの分か決まっていなければ、空いている子に順に
    POST /move   {who, by, x, y, speed}            その場所へ行く(着くか、止まるまで待つ)
    POST /path   {who, by, points:[[x,y],…], speed} 順に通る
    POST /drive  {who, by, left, right, ms}         左右の車輪の速さ(-115〜115)で ms のあいだ走る
    POST /light  {who, color}                       ランプの色(#rrggbb、"" で消す)
    POST /nudge  {who, by, left, right, ms}         コントローラ: 短く走る。手を止めて 3 秒で、ひとまとまりを 1 行に残す
    POST /stop   {who}
    POST /power  {on}                               家で使う / 使わない(使わないなら、つながりをほどく)
    POST /assign {who, name}                        このキューブ(toio-xxx)をこの子の分に
"""

from __future__ import annotations

import asyncio
import json
import os
import struct
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import toio as toio_lib  # noqa: E402

SERVICE = "10b20100-5b3b-4571-9508-cf3efcd7bbae"
CH_ID, CH_MOTOR, CH_LIGHT, CH_SOUND, CH_SENSOR, CH_BUTTON, CH_BATTERY = (
    f"10b2010{n}-5b3b-4571-9508-cf3efcd7bbae" for n in ("1", "2", "3", "4", "6", "7", "8"))
POSTURE = {1: "上向き", 2: "裏返し", 3: "後ろが下", 4: "前が下", 5: "右が下", 6: "左が下"}


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR", Path.home() / "petit_claude"))


class Cube:
    """1 台のキューブ。通知で場所・傾き・ぶつかりを受け取り、走っている間は点を貯める"""

    def __init__(self, address: str, name: str) -> None:
        self.address, self.name = address, name
        self.client = None
        self.battery: int | None = None
        self.pos: dict | None = None          # {"x","y","a"}。マットの外なら None
        self.last_pos: dict | None = None     # マットの上で最後に読めた場所
        self.posture = 1
        self.events: list[dict] = []          # 走っている間の出来事
        self.trail: list[list[float]] | None = None   # 走っている間の点 [秒, x, y, 向き]
        self.t0 = 0.0
        self.move_done: asyncio.Future | None = None
        self.ctrl = 0
        self.lock = asyncio.Lock()
        self.hand: dict | None = None   # 家の人がコントローラで動かしている間 {by, last}

    @property
    def connected(self) -> bool:
        return bool(self.client and self.client.is_connected)

    def _event(self, kind: str, **kw) -> None:
        if self.trail is not None:
            self.events.append({"t": round(time.monotonic() - self.t0, 2), "kind": kind, **kw})

    def on_id(self, _s, data: bytearray) -> None:
        if data[0] == 0x01 and len(data) >= 7:
            x, y, a = struct.unpack_from("<HHH", data, 1)
            if self.pos is None and self.last_pos is not None:
                self._event("found", x=x, y=y)         # マットに戻った
            self.pos = self.last_pos = {"x": x, "y": y, "a": a}
            if self.trail is not None:
                self.trail.append([round(time.monotonic() - self.t0, 2), x, y, a])
        elif data[0] == 0x03:
            if self.pos is not None:
                self._event("lost", **{k: self.pos[k] for k in ("x", "y")})   # 読めなくなる前の最後の場所
            self.pos = None

    def on_motor(self, _s, data: bytearray) -> None:
        if data[0] == 0x83 and len(data) >= 3 and self.move_done and not self.move_done.done() and data[1] == self.ctrl:
            self.move_done.get_loop().call_soon_threadsafe(self.move_done.set_result, data[2])

    def on_battery(self, _s, data: bytearray) -> None:
        if data:
            self.battery = data[0]

    def on_sensor(self, _s, data: bytearray) -> None:
        if data[0] == 0x01 and len(data) >= 5:
            if data[2]:
                self._event("bump")
            if data[4] != self.posture:
                self.posture = data[4]
                self._event("tilt", posture=POSTURE.get(data[4], str(data[4])))

    def state(self) -> dict:
        return {"address": self.address, "name": self.name, "connected": self.connected, "battery": self.battery,
                "pos": self.pos, "last_pos": self.last_pos, "on_mat": self.pos is not None,
                "posture": POSTURE.get(self.posture, str(self.posture)), "busy": self.lock.locked()}


class _Held:
    def __init__(self, address: str, name: str) -> None:
        self.address, self.name = address, name


def _held_by_bluez() -> list[_Held]:
    """PC の Bluetooth(BlueZ)につながったままのキューブ。番人が急に止まると、つながりだけが残り、
    キューブは呼びかけ(青の点滅)をしないので、探しても見つからない。そういう子は、ほどいてから探す"""
    import re
    import subprocess
    try:
        out = subprocess.run(["bluetoothctl", "devices", "Connected"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [_Held(m[1], m[2]) for m in re.finditer(r"Device ([0-9A-F:]{17}) (toio-\S+)", out)]


def _bluez_disconnect(address: str) -> None:
    import subprocess
    try:
        subprocess.run(["bluetoothctl", "disconnect", address], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


class Keeper:
    """3 台までのキューブと、だれの分か(config/toio.json)"""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.cubes: dict[str, Cube] = {}
        self.loop = asyncio.new_event_loop()

    # ---- 家の値 ----
    def config(self) -> dict:
        return toio_lib.load_config(self.base)

    def save_config(self, cfg: dict) -> None:
        p = self.base / "config" / "toio.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")

    def cube_of(self, who: str) -> Cube:
        if not toio_lib.enabled(self.base):
            raise toio_lib.ToioError("toio は、いま家で使わないことになっています(⚙️ 設定で決める)")
        addr = self.config().get("cubes", {}).get(who)
        cube = self.cubes.get(addr or "")
        if cube is None:
            raise toio_lib.ToioError(f"{who} のキューブがつながっていません(電源を入れて、ダッシュボードの 🧊 で「探す」)")
        if not cube.connected:
            raise toio_lib.ToioError(f"{who} のキューブとのつながりが切れています(電源と電池を確かめて「探す」)")
        return cube

    # ---- つなぐ ----
    async def scan(self) -> dict:
        from bleak import BleakClient, BleakScanner
        if not toio_lib.enabled(self.base):
            raise toio_lib.ToioError("toio は、いま家で使わないことになっています(⚙️ 設定で決める)")
        mine = {c.address for c in self.cubes.values() if c.connected}
        stale = [d for d in _held_by_bluez() if d.address not in mine]
        for d in stale:   # 前の番人が残したつながりをほどく。ほどくと、また呼びかけを始めるので見つかる
            await asyncio.to_thread(_bluez_disconnect, d.address)
        if stale:
            await asyncio.sleep(2)
        found = list(await BleakScanner.discover(timeout=6, service_uuids=[SERVICE]))
        for d in found:
            key = d.name or d.address   # 番号(アドレス)は電源を入れ直すと変わることがある。名前 toio-xxx で見分ける
            cube = self.cubes.get(key) or Cube(d.address, key)
            cube.address = d.address
            self.cubes[key] = cube
            if cube.connected:
                continue
            cube.client = BleakClient(d)
            try:
                await cube.client.connect(timeout=10)
                await cube.client.start_notify(CH_ID, cube.on_id)
                await cube.client.start_notify(CH_MOTOR, cube.on_motor)
                await cube.client.start_notify(CH_SENSOR, cube.on_sensor)
                cube.battery = (await cube.client.read_gatt_char(CH_BATTERY))[0]
                await cube.client.start_notify(CH_BATTERY, cube.on_battery)   # 電池は 5 秒ごとに届く
                await cube.client.write_gatt_char(CH_MOTOR, bytes([0x01, 0x01, 0x01, 0x00, 0x02, 0x01, 0x00]), response=True)   # 空の命令(知らせの通り道を開けておく)
            except Exception as e:   # 1 台つながらなくても、ほかは続ける
                print(f"toio: {d.name or 'toio'} につながりませんでした: {e}", file=sys.stderr)
        cfg = self.config()
        owners = cfg.setdefault("cubes", {})
        free = [c for c in toio_lib.petits(self.base) if c not in owners]
        for addr, cube in self.cubes.items():   # だれの分でもないキューブは、空いている子に順に(addr は名前 toio-xxx)
            if cube.connected and addr not in owners.values() and free:
                owners[free.pop(0)] = addr
        self.save_config(cfg)
        for who, addr in owners.items():   # だれの分か分かるように、ランプをその子の色に
            if addr in self.cubes and self.cubes[addr].connected:
                await self.light(self.cubes[addr], toio_lib.color_of(self.base, who))
        return self.status()

    def status(self) -> dict:
        owners = {v: k for k, v in self.config().get("cubes", {}).items()}
        return {"cubes": [{**c.state(), "who": owners.get(a, "")} for a, c in self.cubes.items()], "mat": toio_lib.mat_of(self.config()),
                "on": toio_lib.enabled(self.base)}

    async def power(self, on: bool) -> dict:
        """使う / 使わない。使わないなら、つながりをほどく(キューブはしばらくして眠る)。使うなら探してつなぐ"""
        toio_lib.set_enabled(self.base, on)
        if on:
            return await self.scan()
        await self.close()
        return self.status()

    # ---- 動かす ----
    async def light(self, cube: Cube, color: str) -> None:
        if not color:
            await cube.client.write_gatt_char(CH_LIGHT, bytes([0x01]), response=True)
            return
        r, g, b = toio_lib.led(color)
        await cube.client.write_gatt_char(CH_LIGHT, bytes([0x03, 0x00, 0x01, 0x01, r, g, b]), response=True)

    async def _run(self, cube: Cube, who: str, by: str, cmd: dict, body) -> dict:
        """走っている間の点と出来事を貯めて、終わったら 1 行残す"""
        async with cube.lock:
            cube.trail, cube.events, cube.t0 = [], [], time.monotonic()
            if cube.pos:
                cube.trail.append([0.0, cube.pos["x"], cube.pos["y"], cube.pos["a"]])
            else:
                cube._event("start_off_mat")
            try:
                result = await body()
                await asyncio.sleep(0.2)   # 止まったあとの点も少し
            finally:
                trail, events = cube.trail, cube.events
                cube.trail = None
            run = {"at": datetime.now().isoformat(timespec="seconds"), "who": who, "by": by, "cmd": cmd, "result": result,
                   "seconds": round(time.monotonic() - cube.t0, 2), "trail": toio_lib.thin(trail), "events": events}
            toio_lib.save_run(self.base, run)
            return run

    async def _goto(self, cube: Cube, x: int, y: int, speed: int, timeout: int = 8) -> str:
        cube.ctrl = (cube.ctrl % 250) + 1
        cube.move_done = self.loop.create_future()
        # 目標へ移動: 回りながら進む・速さ一定・向きは変えない(5 << 13)
        pkt = struct.pack("<BBBBBBBHHH", 0x03, cube.ctrl, timeout, 0x00, speed, 0x00, 0x00, x, y, 5 << 13)
        await cube.client.write_gatt_char(CH_MOTOR, pkt, response=True)
        # 着いた知らせ(0x83)を待つ。つないで最初の 1 回は知らせが届かないことがあるので、
        # 目標のすぐそばで 0.6 秒止まっていたら、着いたとみなす
        end, still, last = time.monotonic() + timeout + 2, 0.0, None
        while time.monotonic() < end:
            try:
                code = await asyncio.wait_for(asyncio.shield(cube.move_done), 0.2)
                return toio_lib.MOVE_RESULT.get(code, f"わからない({code})")
            except asyncio.TimeoutError:
                pass
            p = cube.pos
            here = (p["x"], p["y"]) if p else None
            near = here is not None and abs(here[0] - x) <= 6 and abs(here[1] - y) <= 6
            still = still + 0.2 if near and here == last else 0.0
            last = here
            if still >= 0.6:
                return "着いた"
        return toio_lib.MOVE_RESULT[1]

    async def move(self, who: str, by: str, x: int, y: int, speed: int) -> dict:
        cube = self.cube_of(who)
        x, y = toio_lib.check_point(self.config(), x, y)
        speed = toio_lib.clamp_speed(speed)
        return await self._run(cube, who, by, {"move": [x, y], "speed": speed}, lambda: self._goto(cube, x, y, speed))

    async def path(self, who: str, by: str, points: list, speed: int) -> dict:
        cube = self.cube_of(who)
        pts = toio_lib.check_path(self.config(), points)
        speed = toio_lib.clamp_speed(speed)

        async def body() -> str:
            for x, y in pts:
                r = await self._goto(cube, x, y, speed)
                if r != "着いた":
                    return f"{x},{y} の手前で: {r}"
            return "着いた"
        return await self._run(cube, who, by, {"path": pts, "speed": speed}, body)

    async def drive(self, who: str, by: str, left: int, right: int, ms: int) -> dict:
        cube = self.cube_of(who)
        left, right = toio_lib.clamp_wheel(left), toio_lib.clamp_wheel(right)
        ms = max(50, min(int(ms), toio_lib.MAX_DRIVE_MS))

        async def body() -> str:
            pkt = bytes([0x02, 0x01, 1 if left >= 0 else 2, abs(left), 0x02, 1 if right >= 0 else 2, abs(right), min(255, ms // 10)])
            await cube.client.write_gatt_char(CH_MOTOR, pkt, response=False)
            await asyncio.sleep(ms / 1000)
            return "走った"
        return await self._run(cube, who, by, {"drive": [left, right], "ms": ms}, body)

    async def nudge(self, who: str, by: str, left: int, right: int, ms: int = 250) -> dict:
        """コントローラ: 押しているあいだ短く何度も。1 回ずつは残さず、点だけ貯める(とめたら 1 行に)"""
        cube = self.cube_of(who)
        left, right, ms = toio_lib.clamp_wheel(left), toio_lib.clamp_wheel(right), max(50, min(int(ms), 500))
        if cube.lock.locked() and cube.hand is None:
            raise toio_lib.ToioError(f"いま {who} が自分で動かしています。終わってから")
        pkt = bytes([0x02, 0x01, 1 if left >= 0 else 2, abs(left), 0x02, 1 if right >= 0 else 2, abs(right), ms // 10])
        if cube.hand is None:   # 手で動かすひとまとまりの、はじまり
            await cube.lock.acquire()
            cube.trail, cube.events, cube.t0 = [], [], time.monotonic()
            if cube.pos:
                cube.trail.append([0.0, cube.pos["x"], cube.pos["y"], cube.pos["a"]])
            cube.hand = {"by": by, "last": time.monotonic()}
            asyncio.ensure_future(self._hand_watch(cube, who))
        cube.hand["last"] = time.monotonic()
        await cube.client.write_gatt_char(CH_MOTOR, pkt, response=False)
        return {"ok": True, "pos": cube.pos}

    async def _hand_watch(self, cube: Cube, who: str) -> None:
        """手を止めて 3 秒たったら、ひとまとまりを 1 行に残す"""
        while cube.hand and time.monotonic() - cube.hand["last"] < 3:
            await asyncio.sleep(0.5)
        hand, trail, events = cube.hand, cube.trail or [], cube.events
        cube.hand, cube.trail = None, None
        cube.lock.release()
        toio_lib.save_run(self.base, {"at": datetime.now().isoformat(timespec="seconds"), "who": who, "by": hand["by"], "cmd": {"hand": True},
                                      "result": "手で動かした", "seconds": round(hand["last"] - cube.t0, 2), "trail": toio_lib.thin(trail), "events": events})

    async def stop(self, who: str) -> dict:
        cube = self.cube_of(who)
        await cube.client.write_gatt_char(CH_MOTOR, bytes([0x01, 0x01, 0x01, 0x00, 0x02, 0x01, 0x00]), response=False)
        return {"ok": True}

    async def close(self) -> None:
        for cube in self.cubes.values():
            if cube.connected:
                try:
                    await cube.client.disconnect()
                except Exception:
                    pass

    def call(self, coro, timeout: float = 120):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)


def make_handler(keeper: Keeper):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, obj: dict) -> None:
            raw = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a) -> None:   # 1 回ごとの行は出さない
            pass

        def do_GET(self) -> None:
            if self.path.startswith("/cubes"):
                self._send(200, keeper.status())
            else:
                self._send(404, {"error": "ありません"})

        def do_POST(self) -> None:
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                self._send(200, self._do(self.path.split("?")[0], body))
            except toio_lib.ToioError as e:
                self._send(400, {"error": str(e)})
            except Exception as e:
                self._send(500, {"error": f"うまくいきませんでした: {e}"})

        def _do(self, path: str, b: dict) -> dict:
            who, by = str(b.get("who", "")), str(b.get("by") or b.get("who", ""))
            if path == "/power":
                return keeper.call(keeper.power(bool(b.get("on"))), 90)
            if path == "/scan":
                return keeper.call(keeper.scan(), 60)
            if path == "/move":
                return keeper.call(keeper.move(who, by, int(b["x"]), int(b["y"]), int(b.get("speed", 50))))
            if path == "/path":
                return keeper.call(keeper.path(who, by, b.get("points") or [], int(b.get("speed", 50))), 300)
            if path == "/drive":
                return keeper.call(keeper.drive(who, by, int(b.get("left", 0)), int(b.get("right", 0)), int(b.get("ms", 300))))
            if path == "/nudge":
                return keeper.call(keeper.nudge(who, by, int(b.get("left", 0)), int(b.get("right", 0)), int(b.get("ms", 250))), 10)
            if path == "/stop":
                return keeper.call(keeper.stop(who))
            if path == "/light":
                return keeper.call(keeper.light(keeper.cube_of(who), str(b.get("color", "")))) or {"ok": True}
            if path == "/assign":
                cfg = keeper.config()
                cubes = {k: v for k, v in cfg.get("cubes", {}).items() if v != b.get("name")}
                cubes[who] = str(b.get("name", ""))
                cfg["cubes"] = cubes
                keeper.save_config(cfg)
                return keeper.status()
            raise toio_lib.ToioError("その頼み方は分かりません")
    return Handler


def main() -> int:
    keeper = Keeper(data_dir())
    threading.Thread(target=keeper.loop.run_forever, daemon=True).start()
    try:
        if toio_lib.enabled(keeper.base):
            keeper.call(keeper.scan(), 60)   # 起動したら 1 回探す(使うことになっているときだけ)
    except Exception as e:
        print(f"toio: はじめの探索でうまくいきませんでした: {e}", file=sys.stderr)
    import signal

    def bye(*_a) -> None:   # 止めるときは、つながりをほどいてから(残すと、次に探しても見つからない)
        try:
            keeper.call(keeper.close(), 10)
        finally:
            os._exit(0)
    signal.signal(signal.SIGTERM, bye)
    signal.signal(signal.SIGINT, bye)
    port = int(os.environ.get("PETIT_TOIO_PORT", "8774"))
    print(f"toio: 127.0.0.1:{port} で待っています", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), make_handler(keeper)).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
