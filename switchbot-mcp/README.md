# switchbot-mcp

SwitchBot Cloud API（v1.1）をラップするMCPサーバー。プラグ・照明・カーテン・赤外線リモコンなどを操作できる。

## セットアップ

1. SwitchBotアプリ → プロフィール → 設定 → アプリバージョンを10回タップ → 「開発者向けオプション」が出現
2. そこから Token と Secret を取得
3. `.env.example` を参考に環境変数 `SWITCHBOT_TOKEN` / `SWITCHBOT_SECRET` を設定

## ツール

| ツール | 内容 |
|---|---|
| `list_devices` | 登録デバイス一覧（物理デバイス＋赤外線リモコン） |
| `get_device_status` | デバイスの現在の状態（物理デバイスのみ） |
| `send_command` | 任意のコマンドを送る（command/parameter/commandType） |
| `turn_on` / `turn_off` | 電源ON/OFF（プラグ・照明・赤外線家電） |

デバイスIDは `list_devices` で調べる。

## キャラクターへの登録例

`~/petit_claude/characters/<id>/config/autonomous-mcp.json` の `mcpServers` に追加:

```json
"switchbot": {
  "command": "/home/cube-petit/.local/bin/uv",
  "args": ["run", "--directory", "/home/cube-petit/work/embodied-claude/switchbot-mcp", "switchbot-mcp"],
  "env": {
    "SWITCHBOT_TOKEN": "...",
    "SWITCHBOT_SECRET": "..."
  }
}
```

`SWITCHBOT_ALLOWED_TOOLS`（カンマ区切り）で使えるツールを制限できる（m5-mcpと同じ仕組み）。
