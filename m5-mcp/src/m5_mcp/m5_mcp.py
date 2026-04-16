from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent
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
from pathlib import Path

# Support comma-separated hosts for fallback (e.g. "puchiteya.local,10.42.138.101")
_m5_hosts: list[str] = []
_active_host: Optional[str] = None

VOICE_API_HOST = os.environ.get("VOICE_API_HOST", "puchipuchi")
_ASR_URL = f"http://{VOICE_API_HOST}:8765"
_TTS_URL = f"http://{VOICE_API_HOST}:8766"
# GPU PCがつながらないときのフォールバック（localhost:8766）
_TTS_FALLBACK_URL = os.environ.get("TTS_FALLBACK_URL", "http://localhost:8766")
# ダッシュボードは常に同じマシン上で動くので127.0.0.1を使う
_DASHBOARD_URL = f"http://{os.environ.get('DASHBOARD_HOST', '127.0.0.1')}:8765"

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
    return [ImageContent(type="image", data=img_b64, mimeType="image/jpeg")]


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
    """任意の音声ファイルをモノラル16bit 16000Hz WAVに変換してBytesIOで返す。ffmpeg使用。"""
    import subprocess
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out_path = f.name
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", file_path,
                "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
                out_path,
            ],
            capture_output=True,
            check=True,
        )
        buf = io.BytesIO(Path(out_path).read_bytes())
        buf.seek(0)
        return buf
    finally:
        Path(out_path).unlink(missing_ok=True)


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


@mcp.tool()
async def save_to_album(person_id: str, title: str):
    """カメラでスナップショットを撮ってアルバムに保存する。
    person_id: puchiteya / puchiko / puchiru / arisan / kazahaya
    title: 写真のタイトル（例: お散歩、今日の空）
    """
    r = await asyncio.to_thread(lambda: _http_get("/snapshot", timeout=10))
    if r.status_code != 200:
        return "camera failed"
    import requests as _req
    payload = {
        "person_id": person_id,
        "title": title,
        "image_b64": base64.b64encode(r.content).decode(),
    }
    dashboard_url = _DASHBOARD_URL
    resp = await asyncio.to_thread(
        lambda: _req.post(f"{dashboard_url}/api/album/snapshot", json=payload, timeout=15)
    )
    if resp.status_code == 200:
        j = resp.json()
        return {"ok": True, "filename": j.get("filename")}
    return {"ok": False, "status": resp.status_code}


@mcp.tool()
async def lock_album_photo(album_owner_id: str, filename: str):
    """アルバムの写真のロックをトグルする。ロック中の写真は自動削除されない。
    album_owner_id: 写真の持ち主 (puchiteya / puchiko / puchiru / arisan / kazahaya)
    filename: list_albumで取得したファイル名
    戻り値の locked が true ならロック済み、false なら解除済み。
    """
    import requests as _req
    dashboard_url = _DASHBOARD_URL
    resp = await asyncio.to_thread(
        lambda: _req.post(f"{dashboard_url}/api/album/{album_owner_id}/{filename}/lock", timeout=10)
    )
    if resp.status_code == 200:
        return resp.json()
    return {"ok": False, "status": resp.status_code, "body": resp.text}


@mcp.tool()
async def delete_album_photo(filename: str):
    """自分のアルバムから写真を削除する。
    filename: list_albumで取得したファイル名
    削除できるのは自分のアルバムのみ（CHARACTER_IDで判定）。
    """
    person_id = os.environ.get("CHARACTER_ID", "")
    if not person_id:
        return {"ok": False, "error": "CHARACTER_ID が設定されていません"}
    import requests as _req
    dashboard_url = _DASHBOARD_URL
    resp = await asyncio.to_thread(
        lambda: _req.delete(f"{dashboard_url}/api/album/{person_id}/{filename}", timeout=10)
    )
    if resp.status_code == 200:
        return {"ok": True}
    return {"ok": False, "status": resp.status_code, "body": resp.text}


@mcp.tool()
async def list_album(person_id: str, unread_by: str = ""):
    """アルバムの写真一覧を取得する。read_byに誰が見たかが含まれる。
    person_id: puchiteya / puchiko / puchiru / arisan / kazahaya
    unread_by: 指定すると、そのキャラがまだ見ていない写真だけを返す（例: "puchiteya"）
    """
    import requests as _req
    dashboard_url = _DASHBOARD_URL
    resp = await asyncio.to_thread(
        lambda: _req.get(f"{dashboard_url}/api/album/{person_id}", timeout=10)
    )
    if resp.status_code != 200:
        return {"ok": False, "status": resp.status_code}
    photos = resp.json()
    if unread_by:
        photos = [p for p in photos if unread_by not in p.get("read_by", [])]
    return photos


@mcp.tool()
async def view_album_photo(album_owner_id: str, filename: str, viewer_id: str):
    """アルバムの写真を取得して既読にする。写真はbase64で返る。
    album_owner_id: 写真の持ち主 (puchiteya等)
    filename: list_albumで取得したファイル名
    viewer_id: 見ているキャラクターのID (puchiteya等)
    """
    import requests as _req
    dashboard_url = _DASHBOARD_URL
    # 画像取得
    img_resp = await asyncio.to_thread(
        lambda: _req.get(f"{dashboard_url}/api/album/{album_owner_id}/{filename}", timeout=10)
    )
    if img_resp.status_code != 200:
        return {"ok": False, "status": img_resp.status_code}
    img_b64 = base64.b64encode(img_resp.content).decode()
    # 既読記録
    await asyncio.to_thread(
        lambda: _req.post(
            f"{dashboard_url}/api/album/{album_owner_id}/{filename}/read",
            params={"viewer": viewer_id}, timeout=5
        )
    )
    return [ImageContent(type="image", data=img_b64, mimeType="image/jpeg")]


# ===================== ツール：音声合成・音声認識 =====================

_VOICE_SETTINGS_DEFAULT = 6  # WhiteCUL / ノーマル

def _voice_settings_path() -> str:
    char_id = os.environ.get("CHARACTER_ID", "")
    data_dir = os.environ.get("PETIT_DATA_DIR", os.path.join(os.path.expanduser("~"), "petit_claude"))
    return os.path.join(data_dir, "characters", char_id, "voice_settings.json")

def _load_voice_settings() -> dict:
    try:
        with open(_voice_settings_path()) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_voice_settings(settings: dict):
    path = _voice_settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


@mcp.tool()
async def set_voice(
    voicevox_speaker: Optional[int] = None,
    speed_scale: Optional[float] = None,
    pitch_scale: Optional[float] = None,
    intonation_scale: Optional[float] = None,
    volume_scale: Optional[float] = None,
    pre_phoneme_length: Optional[float] = None,
    post_phoneme_length: Optional[float] = None,
):
    """自分の声設定を保存する。以降 speak() でこの設定がデフォルトで使われる。
    指定したパラメータだけ更新される（省略したものは変わらない）。

    voicevox_speaker: おすすめ（中性寄り）
      6=四国めたんツンツン, 23=WhiteCULノーマル, 47=ナースロボＴノーマル, 29=No.7ノーマル
    speed_scale: 話速（0.5〜2.0）
    pitch_scale: 音高（-0.15〜0.15）
    intonation_scale: 抑揚（0〜2.0）
    volume_scale: 音量（0〜2.0）
    pre_phoneme_length: 開始前の無音（秒）
    post_phoneme_length: 終了後の無音（秒）
    """
    settings = _load_voice_settings()
    updates = {
        "voicevox_speaker": voicevox_speaker,
        "speed_scale": speed_scale,
        "pitch_scale": pitch_scale,
        "intonation_scale": intonation_scale,
        "volume_scale": volume_scale,
        "pre_phoneme_length": pre_phoneme_length,
        "post_phoneme_length": post_phoneme_length,
    }
    for k, v in updates.items():
        if v is not None:
            settings[k] = v
    await asyncio.to_thread(_save_voice_settings, settings)
    saved = {k: v for k, v in updates.items() if v is not None}
    return f"声を設定しました: {saved}"


@mcp.tool()
async def speak(
    text: str,
    engine: str = "voicevox",
    # piper
    speaker: int = 0,
    length_scale: float = 1.0,
    noise_scale: float = 0.5,
    noise_w: float = 0.8,
    sentence_silence: float = 0.2,
    # kokoro
    voice: str = "jf_alpha",
    speed: float = 1.0,
    # voicevox
    voicevox_speaker: Optional[int] = None,
    speed_scale: Optional[float] = None,
    pitch_scale: Optional[float] = None,
    intonation_scale: Optional[float] = None,
    volume_scale: Optional[float] = None,
    pre_phoneme_length: Optional[float] = None,
    post_phoneme_length: Optional[float] = None,
    save_as_memo: bool = False,
    memo_title: str = "",
):
    """テキストをTTSで音声合成してM5で再生する。

    engine: "voicevox"（デフォルト）/ "kokoro" / "piper"

    [voicevox]
      voicevox_speaker: 話者番号（省略すると set_voice で設定した声、未設定なら 6）
        6=四国めたんツンツン, 23=WhiteCULノーマル, 47=ナースロボＴノーマル, 29=No.7ノーマル
      speed_scale: 話速（0.5〜2.0）
      pitch_scale: 音高（-0.15〜0.15）
      intonation_scale: 抑揚（0〜2.0）
      volume_scale: 音量（0〜2.0）
      pre_phoneme_length / post_phoneme_length: 前後の無音（秒）
      ※省略したパラメータは set_voice で保存した値を使う
    save_as_memo: Trueにするとダッシュボードのボイスメモにも保存される
    memo_title: ボイスメモのタイトル（省略するとテキストの先頭20文字）

    [kokoro]
      voice: jf_alpha / jf_gongitsune / jf_nezumi / jf_tebukuro / jm_kumo
      speed: 速さ倍率

    [piper]
      speaker: 話者ID（デフォルト0）
      length_scale: 速さ（小さいほど速い）
    """
    # 保存済み設定を読み込み、未指定パラメータのデフォルトに使う
    saved = _load_voice_settings()
    resolved_speaker = voicevox_speaker if voicevox_speaker is not None else saved.get("voicevox_speaker", _VOICE_SETTINGS_DEFAULT)
    resolved_speed = speed_scale if speed_scale is not None else saved.get("speed_scale", 1.0)

    wav_bytes_holder: list[bytes] = []

    def _tts_and_upload():
        if engine == "kokoro":
            payload = {"text": text, "engine": "kokoro", "voice": voice, "speed": speed, "lang": "ja"}
        elif engine == "voicevox":
            payload = {"text": text, "engine": "voicevox", "voicevox_speaker": resolved_speaker, "speed_scale": resolved_speed}
            for key, val, saved_key in [
                ("pitch_scale", pitch_scale, "pitch_scale"),
                ("intonation_scale", intonation_scale, "intonation_scale"),
                ("volume_scale", volume_scale, "volume_scale"),
                ("pre_phoneme_length", pre_phoneme_length, "pre_phoneme_length"),
                ("post_phoneme_length", post_phoneme_length, "post_phoneme_length"),
            ]:
                v = val if val is not None else saved.get(saved_key)
                if v is not None:
                    payload[key] = v
        else:  # piper
            payload = {
                "text": text, "engine": "piper", "speaker": speaker,
                "length_scale": length_scale, "noise_scale": noise_scale,
                "noise_w": noise_w, "sentence_silence": sentence_silence,
            }
        for _tts_url in [_TTS_URL, _TTS_FALLBACK_URL]:
            try:
                r = requests.post(f"{_tts_url}/speak", json=payload, timeout=30)
                r.raise_for_status()
                break
            except (requests.ConnectionError, requests.Timeout):
                if _tts_url == _TTS_FALLBACK_URL:
                    raise
                continue
        wav_bytes = r.content
        if save_as_memo:
            wav_bytes_holder.append(wav_bytes)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp_path = f.name
        try:
            mono_buf = _convert_wav_mono_16k(tmp_path)
            resp = _http_post(
                "/upload_wav", timeout=30,
                files={"file": ("tts_speak.wav", mono_buf, "audio/wav")},
            )
            resp.raise_for_status()
        finally:
            os.unlink(tmp_path)

    await asyncio.to_thread(_tts_and_upload)
    await asyncio.to_thread(lambda: _http_get("/se_play?name=tts_speak.wav", timeout=10))

    if save_as_memo and wav_bytes_holder:
        char_id = os.environ.get("CHARACTER_ID", "unknown")
        title = memo_title or text[:20]
        def _upload_memo():
            requests.post(
                f"{_DASHBOARD_URL}/api/voice_memo/{char_id}/upload",
                data={"title": title},
                files={"file": ("memo.wav", wav_bytes_holder[0], "audio/wav")},
                timeout=15,
            )
        await asyncio.to_thread(_upload_memo)

    return f"spoke: {text}"


@mcp.tool()
async def list_voice_memos(person_id: str, unlistened_by: str = ""):
    """ボイスメモの一覧を取得する。

    person_id: メモの持ち主 (puchiteya / puchiko / puchiru / arisan / kazahaya)
    unlistened_by: 指定するとそのキャラがまだ聴いていないメモだけ返す
    """
    def _fetch():
        dashboard_url = _DASHBOARD_URL
        params = {}
        if unlistened_by:
            params["unlistened_by"] = unlistened_by
        r = requests.get(f"{dashboard_url}/api/voice_memo/{person_id}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    result = await asyncio.to_thread(_fetch)
    return result


@mcp.tool()
async def listen_voice_memo(
    owner_id: str,
    filename: str,
    play_on_m5: bool = False,
    transcribe: bool = False,
):
    """ボイスメモを取得してM5で再生し、既聴として記録する。

    owner_id: メモの持ち主 (puchiteya / puchiko / puchiru / arisan / kazahaya)
    filename: list_voice_memos で取得したファイル名
    play_on_m5: TrueならM5のスピーカーで再生する（デフォルトTrue）
    transcribe: Trueなら音声を文字起こしして返す
    """
    char_id = os.environ.get("CHARACTER_ID", "unknown")

    def _fetch_and_play():
        dashboard_url = _DASHBOARD_URL
        # 音声取得
        r = requests.get(f"{dashboard_url}/api/voice_memo/{owner_id}/{filename}", timeout=15)
        r.raise_for_status()
        audio_bytes = r.content
        ext = Path(filename).suffix.lower()

        transcript = None
        if transcribe:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name
            try:
                wav_buf = _convert_wav_mono_16k(tmp_path)
                asr_r = requests.post(
                    f"{_ASR_URL}/transcribe",
                    files={"file": (Path(filename).stem + ".wav", wav_buf, "audio/wav")},
                    timeout=60,
                )
                asr_r.raise_for_status()
                transcript = asr_r.json().get("text", "")
            except Exception as e:
                transcript = f"(文字起こし失敗: {e})"
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        if play_on_m5:
            # WAV変換してM5にアップロード・再生
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name
            try:
                mono_buf = _convert_wav_mono_16k(tmp_path)
                resp = _http_post(
                    "/upload_wav", timeout=30,
                    files={"file": ("voice_memo.wav", mono_buf, "audio/wav")},
                )
                resp.raise_for_status()
                _http_get("/se_play?name=voice_memo.wav", timeout=10)
            finally:
                os.unlink(tmp_path)

        # 既聴記録
        requests.post(
            f"{dashboard_url}/api/voice_memo/{owner_id}/{filename}/listen",
            params={"listener": char_id},
            timeout=10,
        )
        return transcript

    transcript = await asyncio.to_thread(_fetch_and_play)
    result = f"聴いた: {owner_id}/{filename}"
    if transcript:
        result += f"\n文字起こし: {transcript}"
    return result


@mcp.tool()
async def save_tts_memo(text: str, title: str = ""):
    """テキストをTTS合成してボイスメモに保存する（M5では再生しない）。

    text: 保存したいテキスト
    title: メモのタイトル（省略するとテキストの先頭20文字）
    声の設定は set_voice で保存したものが使われる。
    """
    char_id = os.environ.get("CHARACTER_ID", "unknown")
    saved = _load_voice_settings()
    resolved_speaker = saved.get("voicevox_speaker", _VOICE_SETTINGS_DEFAULT)
    resolved_speed = saved.get("speed_scale", 1.0)

    def _generate_and_upload():
        payload = {"text": text, "engine": "voicevox", "voicevox_speaker": resolved_speaker, "speed_scale": resolved_speed}
        for key, saved_key in [
            ("pitch_scale", "pitch_scale"), ("intonation_scale", "intonation_scale"),
            ("volume_scale", "volume_scale"), ("pre_phoneme_length", "pre_phoneme_length"),
            ("post_phoneme_length", "post_phoneme_length"),
        ]:
            v = saved.get(saved_key)
            if v is not None:
                payload[key] = v
        for _tts_url in [_TTS_URL, _TTS_FALLBACK_URL]:
            try:
                r = requests.post(f"{_tts_url}/speak", json=payload, timeout=30)
                r.raise_for_status()
                break
            except (requests.ConnectionError, requests.Timeout):
                if _tts_url == _TTS_FALLBACK_URL:
                    raise
                continue
        memo_title = title or text[:20]
        requests.post(
            f"{_DASHBOARD_URL}/api/voice_memo/{char_id}/upload",
            data={"title": memo_title},
            files={"file": ("memo.wav", r.content, "audio/wav")},
            timeout=15,
        ).raise_for_status()
        return memo_title

    memo_title = await asyncio.to_thread(_generate_and_upload)
    return f"ボイスメモに保存しました: 「{memo_title}」"


@mcp.tool()
async def lock_voice_memo(owner_id: str, filename: str):
    """ボイスメモのロック/解除をトグルする。ロック中は自動削除されない。

    owner_id: メモの持ち主 (puchiteya / puchiko / puchiru / arisan / kazahaya)
    filename: list_voice_memos で取得したファイル名
    """
    def _toggle():
        r = requests.post(
            f"{_DASHBOARD_URL}/api/voice_memo/{owner_id}/{filename}/lock",
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    result = await asyncio.to_thread(_toggle)
    status = "ロック" if result.get("locked") else "ロック解除"
    return f"{status}しました: {owner_id}/{filename}"


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


@mcp.tool()
async def conversation_relay(to_character: str, message: str, turns_remaining: int = 2):
    """別のぷちにメッセージを渡して会話リレーを開始する。
    自分が speak() で喋ったあとに呼ぶ。

    to_character: 次に話しかける相手 (puchiteya / puchiko / puchiru)
    message: 渡すメッセージ（自分が言った内容）
    turns_remaining: 残りターン数（デフォルト2）
    """
    char_id = os.environ.get("CHARACTER_ID", "unknown")
    dashboard_url = os.environ.get("DASHBOARD_URL", "http://localhost:8765")

    def _relay():
        r = requests.post(
            f"{dashboard_url}/api/relay/start",
            json={"from_char": char_id, "to_char": to_character, "message": message, "turns_remaining": turns_remaining},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    result = await asyncio.to_thread(_relay)
    return f"リレー開始: {to_character} に渡しました ({result})"


# ===================== 感熱紙プリンター (Phomemo M02S / Classic BT RFCOMM) =====================

_PRINTER_ADDR    = os.environ.get("PRINTER_ADDRESS", "")
_PRINTER_CHANNEL = int(os.environ.get("PRINTER_CHANNEL", "1"))
_PRINTER_LOCK    = asyncio.Lock()

# M02S: 57mm paper, 203 DPI, effective print width ~48mm = 384 dots = 48 bytes/row
_PRINT_WIDTH_PX    = 384
_PRINT_WIDTH_BYTES = _PRINT_WIDTH_PX // 8  # 48


def _find_font(size: int):
    from PIL import ImageFont
    for path in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    ]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _render_to_bitmap(text: str, font_size: int) -> tuple[list[bytes], int]:
    """テキストを1bit bitmap に変換して (rows, height) を返す。"""
    from PIL import Image, ImageDraw

    padding = 10
    font = _find_font(font_size)
    img_w = _PRINT_WIDTH_PX

    # 折り返し処理
    dummy = Image.new("1", (img_w, 1))
    draw = ImageDraw.Draw(dummy)
    lines: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line:
            lines.append("")
            continue
        cur = ""
        for ch in raw_line:
            test = cur + ch
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > img_w - padding * 2:
                lines.append(cur)
                cur = ch
            else:
                cur = test
        lines.append(cur)

    line_h = font_size + 4
    img_h = padding + len(lines) * line_h + 200  # 下余白

    img = Image.new("1", (img_w, img_h), 1)  # 白地
    draw = ImageDraw.Draw(img)
    y = padding
    for line in lines:
        draw.text((padding, y), line, font=font, fill=0)
        y += line_h

    raw_rows = []
    for row in range(img_h):
        row_bytes = bytearray(_PRINT_WIDTH_BYTES)
        for col in range(img_w):
            if img.getpixel((col, row)) == 0:  # 黒ピクセル
                row_bytes[col // 8] |= 0x80 >> (col % 8)
        raw_rows.append(bytes(row_bytes))
    return raw_rows, img_h


def _build_print_packet(raw_rows: list[bytes], height: int) -> bytes:
    """ESC/POS コマンド列を生成する。"""
    w_lo = _PRINT_WIDTH_BYTES & 0xFF
    w_hi = (_PRINT_WIDTH_BYTES >> 8) & 0xFF
    h_lo = height & 0xFF
    h_hi = (height >> 8) & 0xFF
    init = b"\x1b\x40"
    cmd  = bytes([0x1d, 0x76, 0x30, 0x00, w_lo, w_hi, h_lo, h_hi])
    data = b"".join(raw_rows)
    feed = b"\n\n\n\n\n\n"
    return init + cmd + data + feed


def _rfcomm_print(addr: str, channel: int, packet: bytes) -> str:
    """RFCOMM ソケットで送信する（Classic BT SPP）。"""
    import socket as _socket
    sock = _socket.socket(_socket.AF_BLUETOOTH, _socket.SOCK_STREAM, _socket.BTPROTO_RFCOMM)
    sock.settimeout(15)
    sock.connect((addr, channel))
    try:
        chunk = 512
        for i in range(0, len(packet), chunk):
            sock.send(packet[i:i+chunk])
        return f"印刷完了 ({len(packet)} bytes)"
    finally:
        sock.close()


@mcp.tool()
async def print_text(text: str, font_size: int = 28) -> str:
    """感熱紙プリンター（Phomemo M02S）でテキストを印刷する。
    PRINTER_ADDRESS 環境変数にBTアドレス（例: 24:70:06:1D:C4:8E）を設定しておくこと。
    font_size: フォントサイズ（デフォルト28）
    """
    addr = _PRINTER_ADDR
    if not addr:
        return "エラー: PRINTER_ADDRESS 環境変数が未設定です（例: 24:70:06:1D:C4:8E）"

    if _PRINTER_LOCK.locked():
        return "プリンターは別のキャラクターが使用中です。少し待ってから再度呼んでください。"

    def _do():
        raw_rows, height = _render_to_bitmap(text, font_size)
        packet = _build_print_packet(raw_rows, height)
        return _rfcomm_print(addr, _PRINTER_CHANNEL, packet)

    async with _PRINTER_LOCK:
        return await asyncio.to_thread(_do)


def _load_image_1bit(image_path: str) -> "Image.Image":
    """画像ファイルを読み込んでプリント幅に合わせた1bit画像を返す。"""
    from PIL import Image
    img = Image.open(image_path).convert("L")  # グレースケール
    # アスペクト比を保ってリサイズ
    w, h = img.size
    new_w = _PRINT_WIDTH_PX
    new_h = int(h * new_w / w)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    # ディザリングして1bit変換
    img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    return img


def _render_text_block(text: str, font_size: int, padding: int = 10) -> "Image.Image":
    """テキストブロックを1bit画像として返す（下余白なし）。"""
    from PIL import Image, ImageDraw
    font = _find_font(font_size)
    img_w = _PRINT_WIDTH_PX

    dummy = Image.new("1", (img_w, 1))
    draw = ImageDraw.Draw(dummy)
    lines: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line:
            lines.append("")
            continue
        cur = ""
        for ch in raw_line:
            test = cur + ch
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > img_w - padding * 2:
                lines.append(cur)
                cur = ch
            else:
                cur = test
        lines.append(cur)

    line_h = font_size + 4
    img_h = padding + len(lines) * line_h + padding
    img = Image.new("1", (img_w, img_h), 1)
    draw = ImageDraw.Draw(img)
    y = padding
    for line in lines:
        draw.text((padding, y), line, font=font, fill=0)
        y += line_h
    return img


def _stack_images(parts: list, bottom_margin: int = 200) -> tuple[list[bytes], int]:
    """複数の1bit画像を縦に結合してビットマップ行リストを返す。"""
    from PIL import Image
    img_w = _PRINT_WIDTH_PX
    total_h = sum(p.height for p in parts) + bottom_margin
    canvas = Image.new("1", (img_w, total_h), 1)
    y = 0
    for part in parts:
        canvas.paste(part, (0, y))
        y += part.height

    raw_rows = []
    for row in range(total_h):
        row_bytes = bytearray(_PRINT_WIDTH_BYTES)
        for col in range(img_w):
            if canvas.getpixel((col, row)) == 0:
                row_bytes[col // 8] |= 0x80 >> (col % 8)
        raw_rows.append(bytes(row_bytes))
    return raw_rows, total_h


@mcp.tool()
async def print_image_text(
    image_path: str,
    text: str = "",
    text_position: str = "bottom",
    font_size: int = 24,
) -> str:
    """画像とテキストを組み合わせて感熱紙プリンター（Phomemo M02S）で印刷する。

    image_path: 印刷する画像ファイルのパス
    text: 一緒に印刷するテキスト（空でも可）
    text_position: テキストの位置 "top"（画像の上）または "bottom"（画像の下、デフォルト）
    font_size: テキストのフォントサイズ（デフォルト24）
    """
    addr = _PRINTER_ADDR
    if not addr:
        return "エラー: PRINTER_ADDRESS 環境変数が未設定です"

    if _PRINTER_LOCK.locked():
        return "プリンターは別のキャラクターが使用中です。少し待ってから再度呼んでください。"

    def _do():
        parts = []
        img_block = _load_image_1bit(image_path)
        if text and text_position == "top":
            parts.append(_render_text_block(text, font_size))
            parts.append(img_block)
        elif text and text_position == "bottom":
            parts.append(img_block)
            parts.append(_render_text_block(text, font_size))
        else:
            parts.append(img_block)

        raw_rows, height = _stack_images(parts)
        packet = _build_print_packet(raw_rows, height)
        return _rfcomm_print(addr, _PRINTER_CHANNEL, packet)

    async with _PRINTER_LOCK:
        return await asyncio.to_thread(_do)


# ===================== Rover =====================
# カンマ区切りで複数URL指定可（例: "http://192.168.8.99,http://192.168.1.99"）
_ROVER_URLS: list[str] = [
    u.strip()
    for u in os.environ.get("ROVER_URL", "http://rover.local").split(",")
    if u.strip()
]


def _rover_get(path: str, timeout: int = 15) -> requests.Response:
    last_exc: Optional[Exception] = None
    for url in _ROVER_URLS:
        try:
            r = requests.get(f"{url}{path}", timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            last_exc = e
    raise last_exc or RuntimeError("ROVER_URL が未設定です")


@mcp.tool()
async def rover_status() -> str:
    """ローバーの状態を確認する（現在のドライバー、移動中かどうか）。"""
    def _do():
        r = _rover_get("/status")
        r.raise_for_status()
        return r.json()
    d = await asyncio.to_thread(_do)
    driver = d.get("driver") or "なし"
    moving = "移動中" if d.get("moving") else "待機中"
    power = "ON" if d.get("motor_power") else "OFF"
    bpct = d.get("battery_pct")
    bv   = d.get("battery_v")
    bat  = f"{bpct}% ({bv}V)" if bpct is not None else "不明"
    return f"ドライバー: {driver} / 状態: {moving} / モーター電源: {power} / バッテリー: {bat}"


@mcp.tool()
async def rover_acquire() -> str:
    """ローバーの操作権を取得する。他のキャラクターが使用中なら失敗する。
    移動前に必ず呼ぶこと。30秒操作がないと自動解放される。
    """
    char_id = os.environ.get("CHARACTER_ID", "unknown")
    def _do():
        r = _rover_get(f"/acquire?driver={char_id}")
        if r.status_code == 409:
            return f"busy:{r.text.split('busy:')[-1]}"
        r.raise_for_status()
        return "ok"
    result = await asyncio.to_thread(_do)
    if result.startswith("busy:"):
        return f"ローバーは {result[5:]} が使用中です。"
    return f"ローバーの操作権を取得しました（{char_id}）。"


@mcp.tool()
async def rover_release() -> str:
    """ローバーの操作権を解放する。移動が終わったら呼ぶこと。"""
    char_id = os.environ.get("CHARACTER_ID", "unknown")
    def _do():
        r = _rover_get(f"/release?driver={char_id}")
        r.raise_for_status()
    await asyncio.to_thread(_do)
    return "ローバーを解放しました。"


@mcp.tool()
async def rover_move(
    direction: str,
    distance_cm: int = 20,
    speed: int = 60,
) -> str:
    """ローバーを移動させる。rover_acquire() で操作権を取得してから呼ぶこと。

    direction: "forward"（前進）/ "backward"（後退）/ "left"（左横移動）/ "right"（右横移動）
    distance_cm: 移動距離（cm、目安）
    speed: 速さ 0-100（デフォルト60）
    """
    def _do():
        r = _rover_get(f"/move?dir={direction}&dist={distance_cm}&speed={speed}")
        r.raise_for_status()
    await asyncio.to_thread(_do)
    dir_ja = {"forward": "前進", "backward": "後退", "left": "左横移動", "right": "右横移動"}.get(direction, direction)
    return f"{dir_ja} {distance_cm}cm 完了。"


@mcp.tool()
async def rover_rotate(
    direction: str,
    angle_deg: int = 90,
    speed: int = 60,
) -> str:
    """ローバーをその場で回転させる。rover_acquire() で操作権を取得してから呼ぶこと。

    direction: "right"（右回転）/ "left"（左回転）
    angle_deg: 回転角度（度、目安）
    speed: 速さ 0-100（デフォルト60）
    """
    def _do():
        r = _rover_get(f"/rotate?dir={direction}&angle={angle_deg}&speed={speed}")
        r.raise_for_status()
    await asyncio.to_thread(_do)
    dir_ja = {"right": "右回転", "left": "左回転"}.get(direction, direction)
    return f"{dir_ja} {angle_deg}度 完了。"


@mcp.tool()
async def rover_sequence(actions: list) -> str:
    """ローバーに複数の動作を順番に実行させる（1回のMCP呼び出しで完結）。
    rover_acquire() で操作権を取得してから呼ぶこと。

    actions: 動作リスト。各要素は以下のいずれか:
      {"action": "move",   "dir": "forward|backward|left|right", "dist": 20, "speed": 60}
      {"action": "rotate", "dir": "right|left", "angle": 90, "speed": 60}
      {"action": "beep",   "freq": 440, "dur": 300, "vol": 255}
      {"action": "stop"}
      {"action": "wait",   "ms": 500}

    例:
      [
        {"action": "move",   "dir": "forward", "dist": 10},
        {"action": "rotate", "dir": "right",   "angle": 90},
        {"action": "beep",   "freq": 523,      "dur": 200},
        {"action": "move",   "dir": "forward", "dist": 10}
      ]
    """
    import json as _json
    total_ms = sum(
        a.get("dist", 20) * 25 if a.get("action") == "move" else
        a.get("angle", 90) * 8 if a.get("action") == "rotate" else
        a.get("dur", 300)      if a.get("action") == "beep" else
        a.get("ms", 500)       if a.get("action") == "wait" else 0
        for a in actions
    )
    timeout = max(15, total_ms // 1000 + 5)
    def _do():
        r = requests.post(
            f"{_ROVER_URL}/sequence",
            json=actions,
            timeout=timeout,
        )
        r.raise_for_status()
    await asyncio.to_thread(_do)
    return f"シーケンス完了: {len(actions)}ステップ"


@mcp.tool()
async def rover_beep(freq: int = 440, duration_ms: int = 300, volume: int = 255) -> str:
    """ローバーのブザーを鳴らす。

    freq: 周波数 Hz（20〜20000、低いほど低音。例: 262=ド, 330=ミ, 440=ラ）
    duration_ms: 長さ ミリ秒（1〜3000）
    volume: 音量 0〜255（デフォルト255=最大）
    """
    freq = max(20, min(20000, freq))
    duration_ms = max(1, min(3000, duration_ms))
    volume = max(0, min(255, volume))
    def _do():
        r = _rover_get(f"/beep?freq={freq}&dur={duration_ms}&vol={volume}", timeout=duration_ms // 1000 + 5)
        r.raise_for_status()
    await asyncio.to_thread(_do)
    return f"ビープ: {freq}Hz / {duration_ms}ms / 音量{volume}"


@mcp.tool()
async def rover_set_speed(speed: int) -> str:
    """ローバーのデフォルト速度を変更する。

    speed: 0-100（現在の設定は rover_status() で確認できる）
    個別の move/rotate 呼び出しで speed を指定しない場合にこの値が使われる。
    """
    speed = max(0, min(100, speed))
    def _do():
        r = _rover_get(f"/speed?value={speed}")
        r.raise_for_status()
        return r.json()
    d = await asyncio.to_thread(_do)
    return f"デフォルト速度を {d.get('default_speed')} に設定しました。"


@mcp.tool()
async def rover_stop() -> str:
    """ローバーを緊急停止する。"""
    def _do():
        r = _rover_get("/stop")
        r.raise_for_status()
    await asyncio.to_thread(_do)
    return "ローバーを停止しました。"


def main():
    mcp.run()
