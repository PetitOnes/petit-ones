#!/usr/bin/env python3
"""
新しいプチキャラクターを追加するセットアップスクリプト。

使い方:
  uv run python create_character.py <id> <name> <color> <m5_host>

例:
  uv run python create_character.py puchitaro ぷちたろう "#f5956e" 10.42.138.102

引数:
  id       : ディレクトリ名・識別子 (英数字, 例: puchitaro)
  name     : 表示名 (例: ぷちたろう)
  color    : テーマカラー (例: "#f5956e")
  m5_host  : M5StackのIPアドレス (例: 10.42.138.102)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
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

## 性格

（ここに{name}の性格を書いてください）

## 口調・話し方

（口調の特徴を書いてください）

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

DEFAULT_SETTINGS = {
    "active_hours": [[7, 0, 8, 0], [12, 0, 13, 0], [18, 0, 24, 0]],
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
        "observe_surroundings": {
            "name_ja": "周りを見たい",
            "description": "カメラで周囲を観察したい",
            "satisfaction_hours": 2.0,
            "keywords": ["take_snapshot", "撮影した", "カメラで"],
            "color": "#7fb3c8",
        },
        "go_outside": {
            "name_ja": "外に出たい",
            "description": "外の世界を体験したい",
            "satisfaction_hours": 72.0,
            "keywords": ["お散歩した", "外に出た", "散歩した"],
            "color": "#a8c9a0",
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
    "priority": ["miss_companion", "browse_curiosity", "observe_surroundings", "go_outside"],
}

MCP_TEMPLATE = {
    "mcpServers": {
        "memory": {
            "command": UV,
            "args": ["run", "--directory", str(PROJECT_DIR / "memory-mcp"), "memory-mcp"],
            "env": {"MEMORY_DB_PATH": ""},  # あとで埋める
        },
        "system-temperature": {
            "command": UV,
            "args": ["run", "--directory", str(PROJECT_DIR / "system-temperature-mcp"), "system-temperature-mcp"],
        },
        "desire-system": {
            "command": UV,
            "args": ["run", "--directory", str(PROJECT_DIR / "desire-system"), "python", "server.py"],
        },
        "m5-mcp": {
            "command": UV,
            "args": ["run", "--directory", str(PROJECT_DIR / "m5-mcp"), "m5-mcp"],
            "env": {"M5_HOST": ""},  # あとで埋める
        },
        "notes": {
            "command": UV,
            "args": ["run", "--directory", str(PROJECT_DIR / "notes-mcp"), "notes-mcp"],
            "env": {"CHARACTER_ID": ""},  # あとで埋める
        },
        "relations": {
            "command": UV,
            "args": ["run", "--directory", str(PROJECT_DIR / "relations-mcp"), "relations-mcp"],
            "env": {
                "CHARACTER_ID": "",  # あとで埋める
                "RELATIONS_PATH": "",  # あとで埋める
                "CHARACTERS_DIR": str(DATA_DIR / "characters"),
            },
        },
    }
}


def create_character(char_id: str, name: str, color: str, m5_host: str) -> None:
    char_dir = CHARACTERS_DIR / char_id

    if char_dir.exists():
        print(f"⚠️  characters/{char_id}/ は既に存在します。上書きしますか？ [y/N] ", end="")
        if input().strip().lower() != "y":
            print("キャンセルしました。")
            return

    char_dir.mkdir(parents=True, exist_ok=True)

    # 1. config.json
    config = {
        "name": name,
        "id": char_id,
        "color": color,
        "color_name": color,  # あとで手動変更可
        "m5_host": m5_host,
        "m5_port": 8081,
        "public": False,
    }
    (char_dir / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  ✓ config.json")

    # 2. SOUL.md
    soul_path = char_dir / "SOUL.md"
    if not soul_path.exists():
        soul_path.write_text(
            SOUL_TEMPLATE.format(name=name, color=color, color_name=color),
            encoding="utf-8",
        )
        print(f"  ✓ SOUL.md （テンプレート。後で編集してください）")
    else:
        print(f"  - SOUL.md は既存のものを保持")

    # 3. settings.json
    settings_path = char_dir / "settings.json"
    if not settings_path.exists():
        settings_path.write_text(
            json.dumps(DEFAULT_SETTINGS, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  ✓ settings.json")
    else:
        print(f"  - settings.json は既存のものを保持")

    # 3b. desire_config.json
    desire_config_path = char_dir / "desire_config.json"
    if not desire_config_path.exists():
        desire_config_path.write_text(
            json.dumps(DEFAULT_DESIRE_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  ✓ desire_config.json （欲求設定テンプレート。後で編集してください）")
    else:
        print(f"  - desire_config.json は既存のものを保持")

    # 4. autonomous-mcp.json
    memory_db = str(Path.home() / ".claude" / "memories" / char_id / "memory.db")
    mcp = json.loads(json.dumps(MCP_TEMPLATE))  # deep copy
    mcp["mcpServers"]["memory"]["env"]["MEMORY_DB_PATH"] = memory_db
    mcp["mcpServers"]["m5-mcp"]["env"]["M5_HOST"] = m5_host
    mcp["mcpServers"]["notes"]["env"]["CHARACTER_ID"] = char_id
    relations_path = str(DATA_DIR / "characters" / char_id / "relations.json")
    mcp["mcpServers"]["relations"]["env"]["CHARACTER_ID"] = char_id
    mcp["mcpServers"]["relations"]["env"]["RELATIONS_PATH"] = relations_path
    (char_dir / "autonomous-mcp.json").write_text(
        json.dumps(mcp, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  ✓ autonomous-mcp.json (M5_HOST={m5_host}, MEMORY_DB_PATH={memory_db})")

    # 5. crontab に追加
    _add_crontab(char_id)

    print(f"\n🎉 {name} ({char_id}) の準備ができました！")
    print(f"\n次のステップ:")
    print(f"  1. characters/{char_id}/SOUL.md を編集して性格を書く")
    print(f"  2. ダッシュボードをリロードすると {name} タブが現れます")


def _add_crontab(char_id: str) -> None:
    char_log_dir = LOG_DIR / char_id
    desire_line = (
        f"*/5  * * * * cd {PROJECT_DIR}/desire-system && "
        f"PETIT_DATA_DIR={DATA_DIR} "
        f"mkdir -p {char_log_dir} && "
        f"{UV} run python desire_updater.py {char_id} >> "
        f"{char_log_dir}/desire-$(date +\\%Y\\%m\\%d).log 2>&1"
    )
    action_line = (
        f"*/20 * * * * {PROJECT_DIR}/autonomous-action.sh {char_id}"
    )

    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current = result.stdout

    added = []
    if desire_line not in current:
        current += desire_line + "\n"
        added.append("desire_updater")
    if action_line not in current:
        current += action_line + "\n"
        added.append("autonomous-action")

    if added:
        proc = subprocess.run(["crontab", "-"], input=current, text=True, capture_output=True)
        if proc.returncode == 0:
            print(f"  ✓ crontab 追加: {', '.join(added)}")
        else:
            print(f"  ⚠️  crontab 追加失敗: {proc.stderr}")
    else:
        print(f"  - crontab は既に設定済み")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)

    _, char_id, name, color, m5_host = sys.argv
    print(f"\n🌟 新しいプチを追加します: {name} ({char_id})")
    print(f"   カラー: {color}  M5: {m5_host}\n")
    create_character(char_id, name, color, m5_host)
