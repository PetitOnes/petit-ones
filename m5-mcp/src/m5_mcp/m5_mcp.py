from mcp.server.fastmcp import FastMCP
import asyncio
import websockets
from websockets.protocol import State as WsState
import json
import requests
import base64
from typing import Optional

mcp = FastMCP("m5")

import os
M5_HOST = os.environ["M5_HOST"]
M5_HTTP = f"http://{M5_HOST}"
M5_WS_URL = f"ws://{M5_HOST}:8080"

# ===================== WS状態 =====================
_ws: Optional[websockets.WebSocketClientProtocol] = None
_ws_lock = asyncio.Lock()
_reader_task: Optional[asyncio.Task] = None
_sensor_data: dict = {}
_touch_queue: asyncio.Queue = asyncio.Queue(maxsize=20)


async def _ensure_ws():
    global _ws, _reader_task
    if _ws is not None and _ws.state == WsState.OPEN:
        return
    async with _ws_lock:
        if _ws is not None and _ws.state == WsState.OPEN:
            return
        _ws = await websockets.connect(M5_WS_URL)
        if _reader_task is not None:
            _reader_task.cancel()
        _reader_task = asyncio.create_task(_ws_reader())


async def _ws_reader():
    global _sensor_data
    try:
        async for message in _ws:
            if isinstance(message, str):
                try:
                    data = json.loads(message)
                    event = data.get("event")
                    if event == "sensors":
                        _sensor_data = data
                    elif event == "touch":
                        if not _touch_queue.full():
                            _touch_queue.put_nowait(data)
                except Exception:
                    pass
            # binary: マイク音声（MIC_STARTしたときだけ流れる、今は無視）
    except Exception:
        pass


async def _send(cmd: str):
    global _ws
    await _ensure_ws()
    try:
        await _ws.send(cmd)
    except Exception:
        # 切断されていたら再接続して再試行
        _ws = None
        await _ensure_ws()
        await _ws.send(cmd)


# ===================== ツール：HTTP系（レスポンス必要） =====================

@mcp.tool()
async def take_snapshot():
    """M5カメラで写真を撮る"""
    r = await asyncio.to_thread(
        lambda: requests.get(f"{M5_HTTP}/snapshot", timeout=10)
    )
    if r.status_code != 200:
        return "camera failed"
    img_b64 = base64.b64encode(r.content).decode()
    return {"image_base64": img_b64, "mime_type": "image/jpeg"}


@mcp.tool()
async def list_faces():
    """SDカードの顔画像ファイル一覧を取得"""
    r = await asyncio.to_thread(
        lambda: requests.get(f"{M5_HTTP}/face_list", timeout=5)
    )
    return r.json()


@mcp.tool()
async def show_face(name: str):
    """顔画像を表示（5秒間）。nameはlist_facesで取得したファイル名"""
    await asyncio.to_thread(
        lambda: requests.get(f"{M5_HTTP}/face_play?name={name}", timeout=5)
    )
    return f"showing face: {name}"


@mcp.tool()
async def list_sounds():
    """SDカードの効果音ファイル一覧を取得"""
    r = await asyncio.to_thread(
        lambda: requests.get(f"{M5_HTTP}/se_list", timeout=5)
    )
    return r.json()


@mcp.tool()
async def get_volume():
    """現在の音量を取得（0〜100）"""
    r = await asyncio.to_thread(
        lambda: requests.get(f"{M5_HTTP}/getvolume", timeout=5)
    )
    return int(r.text)


# ===================== ツール：WS系（fire-and-forget） =====================

@mcp.tool()
async def look(x: int, y: int, mouth: Optional[int] = None):
    """視線を動かす。x/y: -100〜100、mouth: 0〜100（省略可）。5秒後に正面へ戻る"""
    cmd = f"LOOK {x} {y}"
    if mouth is not None:
        cmd += f" {mouth}"
    await _send(cmd)
    return f"looked to x={x}, y={y}"


@mcp.tool()
async def blink(left: bool = False, right: bool = False):
    """ウィンク。left/rightをTrueにすると該当する目を閉じる（0.8秒後に戻る）"""
    await _send(f"BLINK {1 if left else 0} {1 if right else 0}")
    return f"blinked left={left} right={right}"


@mcp.tool()
async def set_face_draw_mode():
    """顔を描画モードに切り替える（目・口をリアルタイム描画）"""
    await _send("MODE draw")
    return "switched to draw mode"


@mcp.tool()
async def set_face_slideshow_mode():
    """顔をスライドショーモードに切り替える（SDのJPEGを3秒ごとに表示）"""
    await _send("MODE jpeg")
    return "switched to slideshow mode"


@mcp.tool()
async def play_sound(name: str):
    """効果音を再生。nameはlist_soundsで取得したファイル名"""
    await _send(f"PLAY {name}")
    return f"played: {name}"


@mcp.tool()
async def set_volume(value: int):
    """音量を設定。value: 0〜100"""
    await _send(f"VOL {value}")
    return f"volume set to {value}"


@mcp.tool()
async def list_icons():
    """表示できるアイコンの一覧を取得"""
    return {"icons": ["love", "cry"]}


@mcp.tool()
async def play_icon(name: str):
    """アイコンを3秒間表示。name: love（ハート）または cry（涙）"""
    await _send(f"ICON {name}")
    return f"icon: {name}"


@mcp.tool()
async def set_face_color(color: str):
    """顔の色をカラーコードで設定。color: '#f5956e' や 'f5956e' など16進数RGB"""
    # '#' を除いて送信
    hex_color = color.lstrip("#")
    await _send(f"COLOR {hex_color}")
    return f"face color set to #{hex_color}"


@mcp.tool()
async def sleep():
    """M5をスリープモードにする（画面暗め、3回タッチまたは明るさで復帰）"""
    await _send("SLEEP")
    return "sleeping"


@mcp.tool()
async def wake():
    """M5をスリープから起こす"""
    await _send("WAKE")
    return "waking up"


# ===================== ツール：マイク制御 =====================

@mcp.tool()
async def mic_start():
    """マイクをオンにしてWS経由で音声ストリームを開始する"""
    await _send("MIC_START")
    return "mic started"


@mcp.tool()
async def mic_stop():
    """マイクをオフにする"""
    await _send("MIC_STOP")
    return "mic stopped"


# ===================== ツール：イベント受信 =====================

@mcp.tool()
async def get_sensor_data():
    """最新のセンサーデータを返す（ambient/proximity/battery/加速度/ジャイロ）"""
    await _ensure_ws()
    if not _sensor_data:
        await asyncio.sleep(0.3)  # 初回は少し待つ
    return _sensor_data


@mcp.tool()
async def wait_for_touch(timeout: float = 10.0):
    """タッチイベントを待つ。timeout秒以内にタッチがなければNoneを返す"""
    await _ensure_ws()
    try:
        data = await asyncio.wait_for(_touch_queue.get(), timeout=timeout)
        return data
    except asyncio.TimeoutError:
        return None


def main():
    mcp.run()
