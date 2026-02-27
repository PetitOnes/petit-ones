"""
Desire Updater - プチの自発的な欲求レベルを計算してJSONに保存する。

SQLite（memory-mcp）から各欲求に関連する最新記憶のタイムスタンプを取得し、
「最後に〇〇してから何時間か」を計算して欲求レベル(0.0〜1.0)を算出する。

cronで5分ごとに実行:
  */5 * * * * cd /path/to/desire-system && uv run python desire_updater.py <character_id>
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # カレントディレクトリの .env
load_dotenv(Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude"))) / ".env")  # DATA_DIR の .env

# キャラクターID（コマンドライン引数 or 環境変数）
import sys
CHARACTER_ID = sys.argv[1] if len(sys.argv) > 1 else os.getenv("CHARACTER_ID", "puchiko")
PROJECT_DIR = Path(os.getenv("PROJECT_DIR", str(Path.home() / "work" / "embodied-claude")))
DATA_DIR = Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))

# SQLite DB パス（memory-mcp が使うパス）
_default_memory_db = str(Path.home() / ".claude" / "memories" / CHARACTER_ID / "memory.db")
MEMORY_DB_PATH = Path(os.getenv("MEMORY_DB_PATH", _default_memory_db))

# 欲求レベル出力先（キャラクター別）
_default_desires_path = str(DATA_DIR / "characters" / CHARACTER_ID / "desires.json")
DESIRES_PATH = Path(os.getenv("DESIRES_PATH", _default_desires_path))

# キャラクター設定（settings.json）を読む
def _load_char_settings() -> dict:
    p = DATA_DIR / "characters" / CHARACTER_ID / "settings.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

_CHAR_SETTINGS = _load_char_settings()

# 一緒にいる人の名前（miss_companion 欲求で使う）
# .env に COMPANION_NAME=コウタ のように設定する
COMPANION_NAME = os.getenv("COMPANION_NAME", "あなた")
_companion_called = f"{COMPANION_NAME}に呼びかけた"
_companion_absent = f"{COMPANION_NAME}がいない"

# 欲求ごとの検索キーワード（記憶のcontentから最新タイムスタンプを探す）
# ★ 「その欲求を満たした行動」の記録だけにマッチするよう、具体的なキーワードにすること
DESIRE_KEYWORDS: dict[str, list[str]] = {
    # 実際に調査・探索した記録（ただの「考えた」は除外）
    "browse_curiosity": [
        "WebSearch", "検索した", "調査した", "論文を", "調べた",
        "発見した", "探した", "調べて",
    ],
    # ありさんと実際に会話・交流した記録
    "miss_companion": [
        f"{COMPANION_NAME}と話した", f"{COMPANION_NAME}に伝えた",
        f"{COMPANION_NAME}と会話", f"{COMPANION_NAME}と話す",
        f"{COMPANION_NAME}が来た", f"{COMPANION_NAME}がいた",
    ],
    # カメラで実際に周囲を撮影した記録
    "observe_surroundings": [
        "take_snapshot", "M5カメラで撮影", "スナップショットを", "カメラで部屋",
        "写真を撮", "周囲を撮", "撮影した",
    ],
    # 実際に外に出た記録
    "go_outside": ["お散歩した", "外に出た", "散歩した", "外出した", "外へ出た"],
}

# 欲求が満たされる間隔（時間）- デフォルト値
# キャラ別の値は settings.json の "desire_hours" で上書きできる
_DEFAULT_SATISFACTION_HOURS: dict[str, float] = {
    "browse_curiosity": 6.0,
    "miss_companion": 4.0,
    "observe_surroundings": 2.0,
    "go_outside": 72.0,
}

# settings.json の desire_hours でマージ
SATISFACTION_HOURS: dict[str, float] = {
    **_DEFAULT_SATISFACTION_HOURS,
    **{k: float(v) for k, v in _CHAR_SETTINGS.get("desire_hours", {}).items()},
}

# キャラ固有の追加欲求を DESIRE_KEYWORDS / SATISFACTION_HOURS に追加
for _name, _cfg in _CHAR_SETTINGS.get("extra_desires", {}).items():
    DESIRE_KEYWORDS[_name] = _cfg.get("keywords", [])
    SATISFACTION_HOURS[_name] = float(_cfg.get("hours", 8.0))


@dataclass
class DesireState:
    """現在の欲求状態。"""

    updated_at: str
    desires: dict[str, float] = field(default_factory=dict)
    dominant: str = "observe_room"

    def to_dict(self) -> dict:
        return {
            "updated_at": self.updated_at,
            "desires": self.desires,
            "dominant": self.dominant,
        }


def get_latest_memory_timestamp(
    db_path: Path,
    keywords: list[str],
) -> datetime | None:
    """
    SQLiteのmemoriesテーブルからキーワードに一致する最新記憶のタイムスタンプを返す。
    一致なければ None。
    """
    if not db_path.exists():
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        # LIKE句でキーワード検索してtimestamp最大値を取得
        conditions = " OR ".join(["content LIKE ?" for _ in keywords])
        params = [f"%{kw}%" for kw in keywords]
        c.execute(f"SELECT MAX(timestamp) FROM memories WHERE {conditions}", params)
        row = c.fetchone()
        conn.close()
    except Exception:
        return None

    if not row or not row[0]:
        return None

    try:
        # memory-mcp は datetime.now()（ローカル時刻・タイムゾーンなし）で保存するので
        # タイムゾーン情報は付けずにそのまま返す
        return datetime.fromisoformat(row[0])
    except ValueError:
        return None


def calculate_desire_level(
    last_satisfied: datetime | None,
    satisfaction_hours: float,
    now: datetime | None = None,
) -> float:
    """
    欲求レベルを 0.0〜1.0 で計算する。
    last_satisfied が None（一度も満たされてない）なら 1.0。
    memory-mcp はローカル時刻（タイムゾーンなし）で保存するので now も同様に扱う。
    """
    if now is None:
        # memory-mcp に合わせてローカル時刻（タイムゾーンなし）を使う
        now = datetime.now()

    if last_satisfied is None:
        return 1.0

    # 両方タイムゾーンなしで統一
    if hasattr(last_satisfied, 'tzinfo') and last_satisfied.tzinfo is not None:
        last_satisfied = last_satisfied.replace(tzinfo=None)
    if hasattr(now, 'tzinfo') and now.tzinfo is not None:
        now = now.replace(tzinfo=None)

    elapsed_hours = (now - last_satisfied).total_seconds() / 3600
    return max(0.0, min(1.0, elapsed_hours / satisfaction_hours))


def compute_desires(
    db_path: Path,
    now: datetime | None = None,
) -> DesireState:
    """全欲求レベルを計算してDesireStateを返す。"""
    if now is None:
        now = datetime.now()  # memory-mcp に合わせてローカル時刻

    desires: dict[str, float] = {}

    for desire_name, keywords in DESIRE_KEYWORDS.items():
        last_ts = get_latest_memory_timestamp(db_path, keywords)
        level = calculate_desire_level(
            last_ts,
            SATISFACTION_HOURS[desire_name],
            now,
        )
        desires[desire_name] = round(level, 3)

    # 最も欲求レベルが高いものを dominant に（同値はキャラの priority 順で決める）
    priority: list[str] = _CHAR_SETTINGS.get("desire_priority", [])
    def _sort_key(k: str) -> tuple:
        rank = priority.index(k) if k in priority else len(priority)
        return (-desires[k], rank)
    dominant = min(desires, key=_sort_key)

    return DesireState(
        updated_at=now.isoformat(),
        desires=desires,
        dominant=dominant,
    )


def save_desires(state: DesireState, path: Path = DESIRES_PATH) -> None:
    """desires.json に保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)


def load_desires(path: Path = DESIRES_PATH) -> DesireState | None:
    """desires.json を読み込む。存在しなければ None。"""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return DesireState(
            updated_at=data["updated_at"],
            desires=data["desires"],
            dominant=data["dominant"],
        )
    except Exception:
        return None


def main() -> None:
    """メインエントリポイント（cronから呼ばれる）。"""
    if not MEMORY_DB_PATH.exists():
        print(f"[desire-updater] memory.db が見つかりません: {MEMORY_DB_PATH}")

    state = compute_desires(MEMORY_DB_PATH)
    save_desires(state)
    now_str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    print(
        f"[{now_str}] [desire-updater] 更新完了: dominant={state.dominant} "
        f"desires={state.desires}"
    )


if __name__ == "__main__":
    main()
