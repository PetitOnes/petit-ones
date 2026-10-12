# ダッシュボード

[README](../README.md) に戻る

## ダッシュボード

- 欲求バー: 各プチの欲求レベルをリアルタイム表示
- チャット: プチに直接話しかける（複数モデル対応: Claude / Gemini / ChatGPT）
- **ターミナル（🖥️）**: ブラウザから Claude Code ターミナル（ttyd）を開く。キャラアイコンを選択して「チャット開始」を押すと `/chat` スキルが自動起動し、プチと SOUL.md ベースのチャットができる。セットアップは [`terminal-setup.md`](terminal-setup.md) を参照
- **だれかと 💬**: 話しかけるプチをトグルで選択して送信。選んだプチ同士で話させることもできる（「✨ 話させる」ボタン）
- **みんなで 🌟**: 全プチに同時送信（M5起動状態も確認できる）
- 設定: アクティブタイム・カメラ/音/マイクの ON/OFF
- 記憶一覧: 日付別の記憶表示
- 日記: 1日のサマリー（毎日23:50に自動生成）
- 交換ノート（📖）: キャラクター・人間全員参加のノート
- アルバム（🖼️）: キャラクター・人間別の写真アルバム（MAX50枚/人、圧縮保存）

### M5タッチメニューフック

M5Stackの2×2タッチメニュー（CAM/SEN/MIC/SET）をタップすると、ダッシュボードの常時監視プロセスが自動応答する。

```
[M5タッチメニュー]
  ├ CAM タップ → dashboard がスナップショット取得（HTTP GET /snapshot）
  │              → Claude CLI でキャラクターが写真を見て感想をメール＋記憶保存
  │              → speak / show_face / play_sound で声・表情・SEを出す
  │
  ├ SEN タップ → dashboard がセンサーデータ取得（HTTP GET /sensors）
  │              → Claude CLI でキャラクターが周囲の状態をメール＋記憶保存
  │              → 同様に声・表情・SEで反応
  │
  └ MIC タップ → M5側でマイク自動起動、PCMバイナリ（16kHz int16）をWSで逐次送信
                  → 無音2秒で自動オフ＋ `mic_end` イベント送信
                  → dashboard がバイナリを蓄積し WAV化 → GPUサーバー（port 8765）でWhisper ASR
                  → 無音（テキスト空）ならスキップ
                  → テキストあり → Claude CLI が speak / メール / 記憶 で応答
```

CAM/SEN/MIC イベントはいずれも `call_claude` 経由で処理され、スピーカーが有効なら `speak` で声・顔・SEで即時リアクションを促す。MIC は GPU サーバー（`VOICE_API_HOST` 環境変数）での ASR が前提。

M5の設定画面（SET → CAM TO）でメール送信先のユーザーを切り替えられる。切り替えた設定は CAM / SEN / MIC の全イベントに反映される（`set_cam_target` WebSocket イベントでダッシュボードに通知）。

ダッシュボード起動時（lifespan）に全キャラ分のウォッチャーが起動し、M5との WebSocket 接続（port 8080）を常時維持・再接続する。

## ダッシュボードの常時起動（systemd）

PC再起動後も自動でダッシュボードが起動するようにする。

### 1. 環境設定ファイルを作成

`~/petit_claude/.env.dashboard` に環境固有の値を書く:

```bash
cat > ~/petit_claude/.env.dashboard <<'EOF'
PETIT_DATA_DIR=/home/yourname/petit_claude
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8765
EOF
```

- `DASHBOARD_HOST`: `0.0.0.0` なら全インタフェースでリッスン。Tailscale IP を指定すると VPN 経由のみアクセス可能
- Tailscale IP の確認: `tailscale ip -4`

### 2. サービスを登録・起動

```bash
sudo cp dashboard/petit-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable petit-dashboard
sudo systemctl start petit-dashboard

# 状態確認
sudo systemctl status petit-dashboard

# ログ確認
journalctl -u petit-dashboard -f
```

## 認証（オプション）

ダッシュボードに Basic 認証 + 7日間セッションを追加できる。

### ロール

| ロール | 閲覧 | チャット・操作 | 設定変更 |
|--------|------|---------------|---------|
| admin | OK | OK | OK |
| operator | OK | OK | NG |
| viewer | OK | NG | NG |

### 設定方法

`~/petit_claude/auth.json` を作成:

```bash
cp dashboard/auth.json.example ~/petit_claude/auth.json
vim ~/petit_claude/auth.json  # パスワードを設定
```

```json
{
  "users": {
    "arisan": {"password": "あなたのパスワード", "role": "admin"},
    "friend": {"password": "友達用パスワード", "role": "operator", "characters": ["puchiko"]},
    "guest": {"password": "ゲスト用パスワード", "role": "viewer"}
  }
}
```

ダッシュボードを再起動すると認証が有効になる。`auth.json` がなければ認証なし（従来通り）。

### キャラクター表示制限

`characters` フィールドで、ユーザーごとに閲覧・操作可能なキャラクターを制限できる。

- `characters` 未設定 or 空配列 → 全キャラ見える
- `characters: ["puchiko"]` → puchiko のみ見える（タブ・チャット・記憶・日記すべて）
- `admin` ロールは `characters` 設定を無視して常に全キャラ見える
- グループチャットも許可キャラのみに送信される
