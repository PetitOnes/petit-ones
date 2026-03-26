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
from pathlib import Path

# Support comma-separated hosts for fallback (e.g. "puchiteya.local,10.42.138.101")
_m5_hosts: list[str] = []
_active_host: Optional[str] = None

VOICE_API_HOST = os.environ.get("VOICE_API_HOST", "puchipuchi")
_ASR_URL = f"http://{VOICE_API_HOST}:8765"
_TTS_URL = f"http://{VOICE_API_HOST}:8766"
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
    return {"image_base64": img_b64, "mime_type": "image/jpeg", "filename": filename}


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
        r = requests.post(f"{_TTS_URL}/speak", json=payload, timeout=30)
        r.raise_for_status()
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
        r = requests.post(f"{_TTS_URL}/speak", json=payload, timeout=30)
        r.raise_for_status()
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


def main():
    mcp.run()
