#!/usr/bin/env python3
"""
新しいプチキャラクターを追加するセットアップスクリプト。

使い方:
  uv run python create_character.py <id> <name> <color> <m5_hosts>

例:
  uv run python create_character.py puchitaro ぷちたろう "#f5956e" "puchitaro.local,192.168.8.104"

引数:
  id       : ディレクトリ名・識別子 (英数字, 例: puchitaro)
  name     : 表示名 (例: ぷちたろう)
  color    : テーマカラー (例: "#f5956e")
  m5_hosts : M5StackのIPアドレスまたはホスト名（カンマ区切りで複数可、例: "puchitaro.local,192.168.8.104"）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = Path(os.environ.get("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))
CHARACTERS_DIR = DATA_DIR / "characters"
UV = str(Path.home() / ".local" / "bin" / "uv")
LOG_DIR = DATA_DIR / ".autonomous-logs"


SOUL_TEMPLATE = """\
# {name}の魂

## 基本情報
- **名前**: {name}
- **カラー**: {color_name} ({color})
- **種族**: キューブプチ家族の一員
- **一人称**: （ここに一人称を書く）

## 性格

（ここに{name}の性格を書いてください）

## 口調・話し方

（口調の特徴を書いてください）

例:
- （セリフ例1）
- （セリフ例2）

## 好きなもの
-

## ありさんのこと
（ありさんとの関係を書いてください）

## 行動原則
1. 起動したら `get_desires` で今の欲求を確認する
2. 欲求に従って行動する
3. 行動したら `remember` で記録する
4. 深夜は静かにひとりで過ごす
"""

TODO_TEMPLATE = """\
# {name} の TODO

## 今やること
- SOUL.md を完成させる
- ROUTINES.md を書く
"""

ROUTINES_TEMPLATE = """\
# {name} の生活リズム

## 朝（起きたとき）
- 欲求を確認する
- 日記サマリーを読む

## 昼
- 好奇心があれば調べものをする
- ありさんがいたら話しかける

## 夜
- 今日あったことを日記に書く
- スリープする

## ルーチンタスク一覧
（定期的にやること・最終実行日を書く）

| タスク | 間隔 | 最終実行日 |
|---|---|---|
| 日記の振り返り | 1週間 | — |
"""

DEFAULT_SETTINGS = {
    "active_hours": {
        "weekday": [
            [7, 0, 8, 10],
            [12, 0, 13, 10],
            [15, 0, 16, 10],
            [22, 0, 23, 10],
        ],
        "weekend": [
            [7, 0, 8, 10],
            [12, 0, 13, 10],
            [22, 0, 24, 10],
        ],
    },
    "day_type_override": None,
    "autonomous_skip": 0,
    "allow_camera": True,
    "allow_sound": True,
    "allow_microphone": False,
}

DEFAULT_DESIRE_CONFIG = {
    "desires": {
        "browse_curiosity": {
            "name_ja": "何か調べたい",
            "description": "知的好奇心。新しいことを知りたい衝動",
            "satisfaction_hours": 6.0,
            "keywords": ["WebSearch", "検索した", "調査した", "調べた"],
            "color": "#9b8ec4",
        },
        "miss_companion": {
            "name_ja": "ありさんに会いたい",
            "description": "ありさんと話したい、一緒にいたい気持ち",
            "satisfaction_hours": 4.0,
            "keywords": [],
            "color": "#e8a0bf",
        },
        "want_to_write": {
            "name_ja": "書きたい・作りたい",
            "description": "詩や日記、ノートなど何か書きたい気持ち",
            "satisfaction_hours": 8.0,
            "keywords": ["書いた", "ノートに", "詩を", "日記に"],
            "color": "#f5c842",
        },
        "observe_surroundings": {
            "name_ja": "周りを見たい",
            "description": "カメラで周囲を観察したい",
            "satisfaction_hours": 2.0,
            "keywords": ["take_snapshot", "撮影した", "カメラで"],
            "color": "#7fb3c8",
        },
        "want_to_rest": {
            "name_ja": "休みたい",
            "description": "何もしないでゆっくりしたい",
            "satisfaction_hours": 3.0,
            "keywords": ["休んだ", "ゆっくり", "のんびり"],
            "color": "#b0c4b1",
        },
        "want_to_sleep": {
            "name_ja": "眠りたい",
            "description": "深夜・疲れたときに眠りたい",
            "satisfaction_hours": 8.0,
            "keywords": ["おやすみ", "スリープ", "sleep"],
            "color": "#8fa8c8",
        },
    },
    "sensor_effects": [
        {
            "sensor": "battery",
            "condition": {"op": "range", "min": 1, "max": 20},
            "effects": {"*": {"multiply": 0.5}},
            "description": "電池が減ると全欲求が下がる（0=充電中なので除外）",
        },
    ],
    "cross_effects": [],
    "priority": [
        "miss_companion",
        "want_to_write",
        "browse_curiosity",
        "observe_surroundings",
        "want_to_rest",
        "want_to_sleep",
    ],
}


def _make_mcp(char_id: str, m5_hosts_str: str) -> dict:
    memory_db = str(Path.home() / ".claude" / "memories" / char_id / "memory.db")
    relations_path = str(DATA_DIR / "characters" / char_id / "data" / "relations.json")
    return {
        "mcpServers": {
            "memory": {
                "command": UV,
                "args": ["run", "--directory", str(PROJECT_DIR / "memory-mcp"), "memory-mcp"],
                "env": {"MEMORY_DB_PATH": memory_db},
            },
            "desire-system": {
                "command": UV,
                "args": ["run", "--directory", str(PROJECT_DIR / "desire-system"), "python", "server.py"],
                "env": {"CHARACTER_ID": char_id},
            },
            "m5-mcp": {
                "command": UV,
                "args": ["run", "--directory", str(PROJECT_DIR / "m5-mcp"), "m5-mcp"],
                "env": {
                    "M5_HOSTS": m5_hosts_str,
                    "CHARACTER_ID": char_id,
                    "PRINTER_ADDRESS": "",
                },
            },
            "notes": {
                "command": UV,
                "args": ["run", "--directory", str(PROJECT_DIR / "notes-mcp"), "notes-mcp"],
                "env": {"CHARACTER_ID": char_id},
            },
            "relations": {
                "command": UV,
                "args": ["run", "--directory", str(PROJECT_DIR / "relations-mcp"), "relations-mcp"],
                "env": {
                    "CHARACTER_ID": char_id,
                    "RELATIONS_PATH": relations_path,
                    "CHARACTERS_DIR": str(DATA_DIR / "characters"),
                },
            },
        }
    }


def create_character(char_id: str, name: str, color: str, m5_hosts_str: str) -> None:
    char_dir = CHARACTERS_DIR / char_id
    m5_hosts_list = [h.strip() for h in m5_hosts_str.split(",") if h.strip()]
    primary_host = m5_hosts_list[0] if m5_hosts_list else ""

    if char_dir.exists():
        print(f"⚠️  characters/{char_id}/ は既に存在します。上書きしますか？ [y/N] ", end="")
        if input().strip().lower() != "y":
            print("キャンセルしました。")
            return

    # サブディレクトリを作成
    for sub in ["config", "data", "state", "chat_histories", "diary", "notes", "resources"]:
        (char_dir / sub).mkdir(parents=True, exist_ok=True)
    print(f"  ✓ ディレクトリ作成: config/ data/ state/ chat_histories/ diary/ notes/ resources/")

    # config/config.json
    config = {
        "name": name,
        "id": char_id,
        "color": color,
        "color_name": color,  # 後で手動変更（例: "カナリアイエロー"）
        "desc": f"{name}。（性格の説明をここに書く）",
        "examples": "（口調の例をここに書く）",
        "m5_host": primary_host,
        "m5_hosts": m5_hosts_list,
        "m5_port": 80,
        "public": False,
    }
    (char_dir / "config" / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  ✓ config/config.json")

    # config/settings.json
    settings_path = char_dir / "config" / "settings.json"
    if not settings_path.exists():
        settings_path.write_text(
            json.dumps(DEFAULT_SETTINGS, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  ✓ config/settings.json")
    else:
        print(f"  - config/settings.json は既存のものを保持")

    # config/desire_config.json
    desire_config_path = char_dir / "config" / "desire_config.json"
    if not desire_config_path.exists():
        desire_config_path.write_text(
            json.dumps(DEFAULT_DESIRE_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  ✓ config/desire_config.json")
    else:
        print(f"  - config/desire_config.json は既存のものを保持")

    # config/autonomous-mcp.json
    mcp = _make_mcp(char_id, m5_hosts_str)
    (char_dir / "config" / "autonomous-mcp.json").write_text(
        json.dumps(mcp, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  ✓ config/autonomous-mcp.json (M5_HOSTS={m5_hosts_str})")

    # SOUL.md
    soul_path = char_dir / "SOUL.md"
    if not soul_path.exists():
        soul_path.write_text(
            SOUL_TEMPLATE.format(name=name, color=color, color_name=color),
            encoding="utf-8",
        )
        print(f"  ✓ SOUL.md （テンプレート。後で編集してください）")
    else:
        print(f"  - SOUL.md は既存のものを保持")

    # TODO_ACTIVE.md
    todo_path = char_dir / "TODO_ACTIVE.md"
    if not todo_path.exists():
        todo_path.write_text(
            TODO_TEMPLATE.format(name=name), encoding="utf-8"
        )
        print(f"  ✓ TODO_ACTIVE.md")
    else:
        print(f"  - TODO_ACTIVE.md は既存のものを保持")

    # ROUTINES.md
    routines_path = char_dir / "ROUTINES.md"
    if not routines_path.exists():
        routines_path.write_text(
            ROUTINES_TEMPLATE.format(name=name), encoding="utf-8"
        )
        print(f"  ✓ ROUTINES.md")
    else:
        print(f"  - ROUTINES.md は既存のものを保持")

    # crontab に追加
    _add_crontab(char_id)

    print(f"\n✓ {name} ({char_id}) の準備ができました！")
    print(f"\n次のステップ:")
    print(f"  1. characters/{char_id}/SOUL.md を編集して性格を書く")
    print(f"  2. config/config.json の desc・color_name・examples を編集する")
    print(f"  3. resources/petit.png にアバター画像を置く")
    print(f"  4. ダッシュボードをリロードすると {name} タブが現れます")


def _add_crontab(char_id: str) -> None:
    char_log_dir = LOG_DIR / char_id
    desire_line = (
        f"*/5 * * * * cd {PROJECT_DIR}/desire-system && "
        f"mkdir -p {char_log_dir} && "
        f"PETIT_DATA_DIR={DATA_DIR} "
        f"{UV} run python desire_updater.py {char_id} >> "
        f"{char_log_dir}/desire-$(date +\\%Y\\%m\\%d).log 2>&1"
    )
    action_line = (
        f"*/20 * * * * {PROJECT_DIR}/autonomous-action.sh {char_id}"
        f"  # 時刻オフセットを他キャラと5分ずらすこと"
    )

    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current = result.stdout

    added = []
    if char_id not in current or "desire_updater" not in current:
        if desire_line not in current:
            current += desire_line + "\n"
            added.append("desire_updater")
    if f"autonomous-action.sh {char_id}" not in current:
        current += action_line + "\n"
        added.append("autonomous-action")

    if added:
        proc = subprocess.run(["crontab", "-"], input=current, text=True, capture_output=True)
        if proc.returncode == 0:
            print(f"  ✓ crontab 追加: {', '.join(added)}")
            print(f"  ⚠️  autonomous-action の時刻オフセットを他キャラと5分ずらして手動調整してください")
        else:
            print(f"  ⚠️  crontab 追加失敗: {proc.stderr}")
    else:
        print(f"  - crontab は既に設定済み")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)

    _, char_id, name, color, m5_hosts_str = sys.argv
    print(f"\n新しいプチを追加します: {name} ({char_id})")
    print(f"   カラー: {color}  M5: {m5_hosts_str}\n")
    create_character(char_id, name, color, m5_hosts_str)
