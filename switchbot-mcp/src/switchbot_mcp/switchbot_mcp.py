from mcp.server.fastmcp import FastMCP
import asyncio
import base64
import hashlib
import hmac
import os
import time
import uuid
import requests

mcp = FastMCP("switchbot")

SWITCHBOT_TOKEN = os.environ.get("SWITCHBOT_TOKEN")
SWITCHBOT_SECRET = os.environ.get("SWITCHBOT_SECRET")
if not SWITCHBOT_TOKEN or not SWITCHBOT_SECRET:
    raise ValueError("SWITCHBOT_TOKEN and SWITCHBOT_SECRET environment variables must be set")

_BASE_URL = "https://api.switch-bot.com/v1.1"


def _auth_headers() -> dict:
    t = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4())
    string_to_sign = f"{SWITCHBOT_TOKEN}{t}{nonce}"
    sign = base64.b64encode(
        hmac.new(SWITCHBOT_SECRET.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "Authorization": SWITCHBOT_TOKEN,
        "sign": sign,
        "t": t,
        "nonce": nonce,
        "Content-Type": "application/json; charset=utf8",
    }


def _get(path: str) -> dict:
    r = requests.get(f"{_BASE_URL}{path}", headers=_auth_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict) -> dict:
    r = requests.post(f"{_BASE_URL}{path}", headers=_auth_headers(), json=body, timeout=10)
    r.raise_for_status()
    return r.json()


@mcp.tool()
async def list_devices():
    """登録されているSwitchBotデバイス一覧を取得（物理デバイス＋赤外線リモコン）"""
    data = await asyncio.to_thread(lambda: _get("/devices"))
    body = data.get("body", {})
    return {
        "devices": body.get("deviceList", []),
        "infrared_remotes": body.get("infraredRemoteList", []),
    }


@mcp.tool()
async def get_device_status(device_id: str):
    """デバイスの現在の状態を取得（物理デバイスのみ対応。赤外線リモコンは非対応）"""
    data = await asyncio.to_thread(lambda: _get(f"/devices/{device_id}/status"))
    return data.get("body", {})


@mcp.tool()
async def send_command(
    device_id: str,
    command: str,
    parameter: str = "default",
    command_type: str = "command",
):
    """デバイスにコマンドを送る。
    command例: turnOn, turnOff, press, setPosition（カーテン）, setAll（エアコン: "温度,モード,風量,電源"）。
    赤外線リモコンに登録したカスタムコマンドを使う場合は command_type="customize" にする。
    """
    body = {"command": command, "parameter": parameter, "commandType": command_type}
    return await asyncio.to_thread(lambda: _post(f"/devices/{device_id}/commands", body))


@mcp.tool()
async def turn_on(device_id: str):
    """デバイスの電源をON（プラグ・照明・赤外線家電など）"""
    body = {"command": "turnOn", "parameter": "default", "commandType": "command"}
    return await asyncio.to_thread(lambda: _post(f"/devices/{device_id}/commands", body))


@mcp.tool()
async def turn_off(device_id: str):
    """デバイスの電源をOFF"""
    body = {"command": "turnOff", "parameter": "default", "commandType": "command"}
    return await asyncio.to_thread(lambda: _post(f"/devices/{device_id}/commands", body))


# SWITCHBOT_ALLOWED_TOOLS が設定されている場合、リスト外のツールを除外する
_allowed_tools_env = os.environ.get("SWITCHBOT_ALLOWED_TOOLS")
if _allowed_tools_env:
    _allowed = set(_allowed_tools_env.split(","))
    for _name in list(mcp._tool_manager._tools.keys()):
        if _name not in _allowed:
            mcp.remove_tool(_name)


def main():
    mcp.run()
