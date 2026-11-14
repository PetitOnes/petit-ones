#!/usr/bin/env python3
"""OMRON 2JCIE-BU01(USB 環境センサー)を読む。気温・湿度・明るさ・気圧・騒音・eTVOC・eCO2。

PC に差すと USB(0590:00d4)として見えるが、Linux は標準ではシリアルにしないので、udev の決まりで
ftdi_sio に ID を教え、/dev/omron-env の名前で読めるようにしてある(/etc/udev/rules.d/99-omron-2jcie-bu.rules)。

話し方(OMRON のマニュアル): 115200 8N1。フレームは 52 42 | 長さ(2, LE) | 命令(01 読む) | 番地(2, LE) | データ | CRC-16(2, LE)。
番地 0x5021「Latest data Long」で、いちばん新しい値がまとめて返る。CRC は MODBUS(初期値 0xFFFF、多項式 0xA001)。

Usage:
    python3 omron_env.py read [--port /dev/omron-env] [--json]
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import time

DEFAULT_PORT = "/dev/omron-env"
BAUD = 115200
ADDR_LATEST_LONG = 0x5021


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def frame_read(addr: int) -> bytes:
    body = bytes([0x01]) + struct.pack("<H", addr)
    head = b"\x52\x42" + struct.pack("<H", len(body) + 2)
    f = head + body
    return f + struct.pack("<H", crc16(f))


def parse_latest_long(payload: bytes) -> dict:
    """番地 0x5021 のデータ部(番地のあと)。並びは OMRON のマニュアル 4.5.2 Latest data Long"""
    seq, temp, hum, light, press, noise, etvoc, eco2, discomfort, heat = struct.unpack_from("<BhhhihhhhH", payload, 0)
    return {
        "seq": seq,
        "temperature": round(temp / 100, 2),      # ℃
        "humidity": round(hum / 100, 2),          # %RH
        "light": light,                           # lx
        "pressure": round(press / 1000, 2),       # hPa
        "noise": round(noise / 100, 2),           # dB
        "etvoc": etvoc,                           # ppb
        "eco2": eco2,                             # ppm
        "discomfort": round(discomfort / 100, 2),
        "heat_stroke": round(heat / 100, 2),      # ℃
    }


def read(port: str = DEFAULT_PORT, timeout: float = 2.0) -> dict:
    """1 回読む。読めなければ例外(OSError / ValueError)"""
    import serial  # pyserial(この PC にはある)
    with serial.Serial(port, BAUD, timeout=timeout) as s:
        s.reset_input_buffer()
        s.write(frame_read(ADDR_LATEST_LONG))
        s.flush()
        deadline = time.monotonic() + timeout
        buf = b""
        while time.monotonic() < deadline:
            buf += s.read(128)
            i = buf.find(b"\x52\x42")
            if i >= 0 and len(buf) >= i + 4:
                length = struct.unpack_from("<H", buf, i + 2)[0]
                if len(buf) >= i + 4 + length:
                    frame = buf[i:i + 4 + length]
                    break
        else:
            raise ValueError("応答が来ない")
    if struct.unpack("<H", frame[-2:])[0] != crc16(frame[:-2]):
        raise ValueError("CRC が合わない")
    cmd = frame[4]
    if cmd != 0x01:
        raise ValueError(f"センサーがエラーを返した(0x{cmd:02x})")
    return parse_latest_long(frame[7:-2])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read")
    r.add_argument("--port", default=DEFAULT_PORT)
    r.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        d = read(a.port)
    except Exception as e:   # noqa: BLE001
        print(f"読めない: {e}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(d, ensure_ascii=False))
    else:
        print(f"🌡 {d['temperature']}℃ 💧 {d['humidity']}% ☀️ {d['light']} lx 🌀 {d['pressure']} hPa 🔊 {d['noise']} dB  eCO2 {d['eco2']} ppm  eTVOC {d['etvoc']} ppb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
