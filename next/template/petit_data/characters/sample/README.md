# サンプルキャラクター

自分のぷちを作るための雛形です。中身に実在のキャラクターの人格・設定は入っていません。

## 使い方

1. このディレクトリを `repos/../` ではなく、コンテナがマウントするデータ側
   (`.env` の `PETIT_DATA_DIR` に対応するホスト側ディレクトリ、例えば
   `./petit-data/characters/`)に、キャラクターID名でコピーする

   ```bash
   mkdir -p petit-data/characters
   cp -r sample-character petit-data/characters/alice
   ```

2. `characters/alice/config/config.json` を編集する
   - `character_id` / `display_name`
   - `m5_host`: 自分のM5のIPアドレス(`192.168.x.x`)
3. `characters/alice/config/autonomous-mcp.json` の `alice` / IPアドレスを、
   実際のキャラクターID・M5のIPに書き換える
4. `characters/alice/config/settings.json` の `active_hours` などを好みに調整する
5. `characters/alice/SOUL.md` に人格を書く(いちばん大事なファイル)
6. `.env` の `CHARACTER_IDS` に `alice`(自分が付けたキャラクターID)を追加する

## ディレクトリの中身

```
config/
  config.json           # M5ホスト・表示名など
  settings.json         # 自律行動の頻度・アクティブ時間・許可設定
  autonomous-mcp.json   # 自律行動時に使うMCPサーバー設定
SOUL.md                  # 人格の核(必ず書く)
ROUTINES.md              # ルーチン行動の一覧(任意)
TODO_ACTIVE.md           # 今やること(任意)
```

自律行動が始まると、`state/` や `logs/` などのディレクトリが自動的に作られます。
