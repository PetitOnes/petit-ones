"""各キャラのTTS音声を生成して話者認識に登録するスクリプト。

使い方:
  python3 register_tts_voices.py [--chars puchiteya puchiko puchiru] [--tts-url ...] [--asr-url ...]
"""

import argparse
import json
import os
import tempfile
from pathlib import Path

import requests

CHARACTERS = ["puchiteya", "puchiko", "puchiru"]

# 登録用テキスト（複数で精度UP）
REGISTRATION_TEXTS = [
    "こんにちは、わたしの名前はぷちです。よろしくお願いします。",
    "今日もよい一日になりますように。空はとても青くて気持ちがいいです。",
    "ありさん、ただいま。何か面白いことありましたか？",
]

DEFAULT_TTS_URL = os.environ.get("TTS_URL", "http://100.101.241.50:8766")
DEFAULT_ASR_URL = os.environ.get("ASR_URL", "http://100.101.241.50:8765")
PETIT_DATA_DIR = Path(os.environ.get("PETIT_DATA_DIR", Path.home() / "petit_claude"))
VOICE_SETTINGS_DEFAULT = {"voicevox_speaker": 6}


def load_voice_settings(char_id: str) -> dict:
    path = PETIT_DATA_DIR / "characters" / char_id / "voice_settings.json"
    try:
        return json.loads(path.read_text())
    except Exception:
        return VOICE_SETTINGS_DEFAULT


def generate_tts(text: str, settings: dict, tts_url: str) -> bytes:
    payload = {
        "text": text,
        "engine": "voicevox",
        "voicevox_speaker": settings.get("voicevox_speaker", 6),
        "speed_scale": settings.get("speed_scale", 1.0),
    }
    for key in ("pitch_scale", "intonation_scale", "volume_scale", "pre_phoneme_length", "post_phoneme_length"):
        if key in settings:
            payload[key] = settings[key]

    r = requests.post(f"{tts_url}/speak", json=payload, timeout=30)
    r.raise_for_status()
    return r.content


def register_speaker(char_id: str, wav_bytes: bytes, asr_url: str) -> dict:
    r = requests.post(
        f"{asr_url}/register_speaker",
        data={"speaker_id": char_id},
        files={"file": ("voice.wav", wav_bytes, "audio/wav")},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def main():
    parser = argparse.ArgumentParser(description="Register TTS voices for speaker recognition")
    parser.add_argument("--chars", nargs="+", default=CHARACTERS)
    parser.add_argument("--tts-url", default=DEFAULT_TTS_URL)
    parser.add_argument("--asr-url", default=DEFAULT_ASR_URL)
    args = parser.parse_args()

    for char_id in args.chars:
        print(f"\n=== {char_id} ===")
        settings = load_voice_settings(char_id)
        print(f"  voice settings: {settings}")

        for i, text in enumerate(REGISTRATION_TEXTS, 1):
            print(f"  [{i}/{len(REGISTRATION_TEXTS)}] TTS生成中: {text[:20]}...")
            try:
                wav_bytes = generate_tts(text, settings, args.tts_url)
                result = register_speaker(char_id, wav_bytes, args.asr_url)
                print(f"  → 登録完了: {result}")
            except Exception as e:
                print(f"  → エラー: {e}")

    print("\n完了。登録済み話者:")
    try:
        r = requests.get(f"{args.asr_url}/speakers", timeout=10)
        print(" ", r.json())
    except Exception as e:
        print(f"  確認エラー: {e}")


if __name__ == "__main__":
    main()
