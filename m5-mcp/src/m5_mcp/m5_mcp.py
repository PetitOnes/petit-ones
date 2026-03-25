from mcp.server.fastmcp import FastMCP
import asyncio
import websockets
from websockets.protocol import State as WsState
import json
import requests
import base64
import io
import wave
import struct
from typing import Optional

mcp = FastMCP("m5")

import os
import tempfile

# Support comma-separated hosts for fallback (e.g. "puchiteya.local,10.42.138.101")
_m5_hosts: list[str] = []
_active_host: Optional[str] = None

VOICE_API_HOST = os.environ.get("VOICE_API_HOST", "puchipuchi")
_ASR_URL = f"http://{VOICE_API_HOST}:8765"
_TTS_URL = f"http://{VOICE_API_HOST}:8766"

def _init_hosts():
    global _m5_hosts
    raw = os.environ.get("M5_HOSTS", "") or os.environ.get("M5_HOST", "")
    _m5_hosts = [h.strip() for h in raw.split(",") if h.strip()]
    if not _m5_hosts:
        raise ValueError("M5_HOST or M5_HOSTS environment variable must be set")

_init_hosts()


def _http_get(path: str, timeout: int = 5, **kwargs) -> requests.Response:
    """HTTP GET with host fallback."""
    global _active_host
    hosts = []
    if _active_host:
        hosts.append(_active_host)
    hosts.extend(h for h in _m5_hosts if h != _active_host)

    last_exc: Optional[Exception] = None
    for host in hosts:
        try:
            r = requests.get(f"http://{host}{path}", timeout=timeout, **kwargs)
            _active_host = host
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            continue
    raise last_exc or ConnectionError(f"All hosts unreachable: {hosts}")


def _http_post(path: str, timeout: int = 5, **kwargs) -> requests.Response:
    """HTTP POST with host fallback."""
    global _active_host
    hosts = []
    if _active_host:
        hosts.append(_active_host)
    hosts.extend(h for h in _m5_hosts if h != _active_host)

    last_exc: Optional[Exception] = None
    for host in hosts:
        try:
            r = requests.post(f"http://{host}{path}", timeout=timeout, **kwargs)
            _active_host = host
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            continue
    raise last_exc or ConnectionError(f"All hosts unreachable: {hosts}")


# ===================== WS状態 =====================
_ws: Optional[websockets.WebSocketClientProtocol] = None
_ws_lock = asyncio.Lock()
_reader_task: Optional[asyncio.Task] = None
_sensor_data: dict = {}
_touch_queue: asyncio.Queue = asyncio.Queue(maxsize=20)
_menu_queue: asyncio.Queue = asyncio.Queue(maxsize=20)


async def _ensure_ws():
    global _ws, _reader_task, _active_host
    if _ws is not None and _ws.state == WsState.OPEN:
        return
    async with _ws_lock:
        if _ws is not None and _ws.state == WsState.OPEN:
            return
        # Try each host for WebSocket connection
        hosts = []
        if _active_host:
            hosts.append(_active_host)
        hosts.extend(h for h in _m5_hosts if h != _active_host)

        last_exc: Optional[Exception] = None
        for host in hosts:
            try:
                _ws = await websockets.connect(f"ws://{host}:8080")
                _active_host = host
                break
            except Exception as e:
                last_exc = e
                continue
        else:
            raise last_exc or ConnectionError(f"WS: all hosts unreachable: {hosts}")

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
                    elif event == "menu_select":
                        if not _menu_queue.full():
                            _menu_queue.put_nowait(data)
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
    r = await asyncio.to_thread(lambda: _http_get("/snapshot", timeout=10))
    if r.status_code != 200:
        return "camera failed"
    img_b64 = base64.b64encode(r.content).decode()
    return {"image_base64": img_b64, "mime_type": "image/jpeg"}


@mcp.tool()
async def list_faces():
    """SDカードの顔画像ファイル一覧を取得"""
    r = await asyncio.to_thread(lambda: _http_get("/face_list"))
    return r.json()


@mcp.tool()
async def show_face(name: str):
    """顔画像を表示（5秒間）。nameはlist_facesで取得したファイル名"""
    await asyncio.to_thread(
        lambda: _http_get(f"/face_play?name={name}")
    )
    return f"showing face: {name}"


@mcp.tool()
async def list_sounds():
    """SDカードの効果音ファイル一覧を取得"""
    r = await asyncio.to_thread(lambda: _http_get("/se_list"))
    return r.json()


@mcp.tool()
async def get_volume():
    """現在の音量を取得（0〜100）"""
    r = await asyncio.to_thread(lambda: _http_get("/getvolume"))
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
    await asyncio.to_thread(lambda: _http_get(f"/se_play?name={name}"))
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
    """M5をスリープモードにする（画面暗め、3回タッチで復帰）"""
    await _send("SLEEP")
    return "sleeping"


@mcp.tool()
async def wake():
    """M5をスリープから起こす"""
    await _send("WAKE")
    return "waking up"


# ===================== ツール：輝度・省電力 =====================

@mcp.tool()
async def set_brightness(value: int):
    """画面の輝度を設定。value: 0〜100"""
    await _send(f"BRIGHTNESS {value}")
    return f"brightness set to {value}"


@mcp.tool()
async def get_brightness():
    """現在の画面輝度を取得（0〜100）"""
    r = await asyncio.to_thread(lambda: _http_get("/getbrightness"))
    return int(r.text)


@mcp.tool()
async def set_power_save(enabled: bool):
    """省電力モードの切替。ONで輝度制限+描画10fps"""
    await _send(f"POWERSAVE {'ON' if enabled else 'OFF'}")
    return f"power save {'on' if enabled else 'off'}"


@mcp.tool()
async def get_power_save():
    """省電力モードの状態を取得"""
    r = await asyncio.to_thread(lambda: _http_get("/getpowersave"))
    return r.text == "true"


@mcp.tool()
async def batch_commands(commands: list[str]):
    """複数のコマンドをまとめて送信する。例: ["BRIGHTNESS 5", "VOL 0", "POWERSAVE ON"]"""
    for cmd in commands:
        await _send(cmd)
    return f"sent {len(commands)} commands"


# ===================== ツール：ファイルアップロード =====================

def _convert_wav_mono_16k(file_path: str) -> io.BytesIO:
    """WAVをモノラル16bit 16000Hzに変換してBytesIOで返す。既に条件を満たしていればそのまま。"""
    with wave.open(file_path, "rb") as src:
        n_channels = src.getnchannels()
        sampwidth = src.getsampwidth()
        framerate = src.getframerate()
        n_frames = src.getnframes()
        raw = src.readframes(n_frames)

    # 16bit PCMに統一
    if sampwidth == 1:
        # 8bit unsigned → 16bit signed
        samples = [(b - 128) * 256 for b in raw]
    elif sampwidth == 2:
        samples = list(struct.unpack(f"<{len(raw)//2}h", raw))
    elif sampwidth == 3:
        samples = []
        for i in range(0, len(raw), 3):
            val = int.from_bytes(raw[i:i+3], "little", signed=True)
            samples.append(val >> 8)
    elif sampwidth == 4:
        raw32 = struct.unpack(f"<{len(raw)//4}i", raw)
        samples = [s >> 16 for s in raw32]
    else:
        samples = list(struct.unpack(f"<{len(raw)//2}h", raw))

    # ステレオ→モノラル（チャンネル平均）
    if n_channels > 1:
        mono = []
        for i in range(0, len(samples), n_channels):
            avg = sum(samples[i:i+n_channels]) // n_channels
            mono.append(avg)
        samples = mono

    # リサンプル（簡易線形補間）
    target_rate = 16000
    if framerate != target_rate:
        ratio = framerate / target_rate
        new_len = int(len(samples) / ratio)
        resampled = []
        for i in range(new_len):
            src_pos = i * ratio
            idx = int(src_pos)
            frac = src_pos - idx
            if idx + 1 < len(samples):
                val = int(samples[idx] * (1 - frac) + samples[idx + 1] * frac)
            else:
                val = samples[idx]
            resampled.append(max(-32768, min(32767, val)))
        samples = resampled

    # WAVとして書き出し
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(target_rate)
        out.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    buf.seek(0)
    return buf


@mcp.tool()
async def upload_wav(file_path: str):
    """WAVファイルをM5のSDカードにアップロード。自動でモノラル16bit 16kHzに変換される"""
    def _upload():
        mono_buf = _convert_wav_mono_16k(file_path)
        filename = file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return _http_post(
            "/upload_wav",
            timeout=30,
            files={"file": (filename, mono_buf, "audio/wav")},
        )
    r = await asyncio.to_thread(_upload)
    if r.status_code == 200:
        return f"uploaded (converted to mono 16kHz): {file_path}"
    return f"upload failed: {r.status_code}"


@mcp.tool()
async def upload_face(file_path: str):
    """顔画像(JPG)をM5のSDカードにアップロード。file_path: ローカルのJPGファイルパス"""
    def _upload():
        with open(file_path, "rb") as f:
            return _http_post("/upload_face", timeout=30, files={"file": f})
    r = await asyncio.to_thread(_upload)
    if r.status_code == 200:
        return f"uploaded: {file_path}"
    return f"upload failed: {r.status_code}"


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
    """最新のセンサーデータを返す（ambient/proximity/battery/voltage/rssi/加速度/ジャイロ）"""
    try:
        r = await asyncio.to_thread(lambda: _http_get("/sensors"))
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    # フォールバック: WSから取得
    await _ensure_ws()
    if not _sensor_data:
        await asyncio.sleep(0.3)
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


@mcp.tool()
async def wait_for_menu_select(timeout: float = 30.0):
    """M5のタッチメニューで項目が選択されるのを待つ。
    camera選択時はスナップショット(base64)がdataフィールドに含まれる。
    sensor選択時は最新のセンサーデータがsensorsフィールドに含まれる。
    mic選択時はM5側でマイクが自動起動済み。
    timeout秒以内に選択がなければNoneを返す。
    item: 'camera' | 'sensor' | 'mic'
    """
    await _ensure_ws()
    try:
        data = await asyncio.wait_for(_menu_queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None

    # sensor: WSリーダーが常時更新しているキャッシュを付与
    if data.get("item") == "sensor" and _sensor_data:
        data["sensors"] = _sensor_data

    return data


# ===================== ツール：音声合成・音声認識 =====================

@mcp.tool()
async def speak(
    text: str,
    speaker: int = 0,
    length_scale: float = 1.0,
    noise_scale: float = 0.5,
    noise_w: float = 0.8,
    sentence_silence: float = 0.2,
):
    """テキストをTTSで音声合成してM5で再生する。
    speaker: 話者ID。length_scale: 小さいほど速い。noise_scale: 声のバリエーション。
    noise_w: 音素長のバリエーション。sentence_silence: 文間の無音時間(秒)。
    """
    def _tts_and_upload():
        # TTS → WAVバイナリ取得
        payload = {
            "text": text,
            "speaker": speaker,
            "length_scale": length_scale,
            "noise_scale": noise_scale,
            "noise_w": noise_w,
            "sentence_silence": sentence_silence,
        }
        r = requests.post(f"{_TTS_URL}/speak", json=payload, timeout=30)
        r.raise_for_status()
        wav_bytes = r.content

        # 一時ファイルに保存してM5にアップロード
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp_path = f.name

        try:
            mono_buf = _convert_wav_mono_16k(tmp_path)
            resp = _http_post(
                "/upload_wav",
                timeout=30,
                files={"file": ("tts_speak.wav", mono_buf, "audio/wav")},
            )
            resp.raise_for_status()
        finally:
            os.unlink(tmp_path)

    await asyncio.to_thread(_tts_and_upload)
    await asyncio.to_thread(lambda: _http_get("/se_play?name=tts_speak.wav", timeout=10))
    return f"spoke: {text}"


@mcp.tool()
async def transcribe_audio(file_path: str):
    """ローカルのWAVファイルを音声認識してテキストを返す"""
    def _transcribe():
        with open(file_path, "rb") as f:
            r = requests.post(
                f"{_ASR_URL}/transcribe",
                files={"file": (os.path.basename(file_path), f, "audio/wav")},
                timeout=60,
            )
            r.raise_for_status()
            return r.json()
    result = await asyncio.to_thread(_transcribe)
    return result


def main():
    mcp.run()
