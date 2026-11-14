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
- 日記: 1日のサマリー（毎日23:50に自動生成）。材料はその日の記憶と、ぷちログの出来事（持ち上げられた・置かれた・だれと何回話した・ひとりの時間に何をしたか。中身は写さない）
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

## 家の設定（`config/ui.json`）

家ぜんたいの見た目と使い方の設定。置き場所は `PETIT_DATA_DIR/config/ui.json`（git には入れない）。ダッシュボードの ⚙️（「みんな」「だれか」のとき）から変えられる。

| 項目 | 中身 |
|---|---|
| `topbar_color` | トップバーの色（`#rrggbb`）。無ければ、選んでいるぷちの色 |
| `house_title` | トップバーの題。無ければ「`<COMPANION_NAME>`ち」 |
| `tools` | 道具の列の並び。`[{"id": "album", "show": true}, …]` の順。`show: false` は「ほか」の中 |
| `send_key` | 話しかける欄の送り方。`enter`（Enter で送信）か `ctrl_enter`（Ctrl+Enter で送信、Enter は改行） |

## 部品とページ（`dashboard/ui/`）

見た目の部品は `dashboard/ui/` に分けて置く。新しいページはここに 1 ページ 1 ファイルで足し、`main.py` には経路だけを書く。

| ファイル | 中身 |
|---|---|
| `tokens.css` | 色・角丸・余白・文字（デザイントークン）。部品はこの名前だけを使う |
| `atoms.css` / `molecules.css` | 原子（ボタン・入力欄・スイッチなど、`a-`）と分子（カード・設定の行など、`m-`） |
| `pages.css` / `page.js` | `ui/` のページの枠組みと共通の下ごしらえ |
| `embed.css` | 古いページ（アルバム・ボイスメモ・ノート・交換日記・ライブラリ）を、トップページの会話の場所に出すときの配色 |
| `md.js` | markdown を HTML にしたあとの後始末 |
| `petitlog.html` / `diary.html` | ぷちログ（1 日のタイムライン）と日記の一覧。データの組み立ては `dashboard/petit_log.py`（読むだけ） |
| 右上の 📍 | いま どこ。わたしのいま（自室・お外・会社 など）を決めると `PETIT_DATA_DIR/state/whereabouts.json` に、ログインの人ごとの一言と、決めた時刻(since)・いつまでか(until。1・3・8 時間か「消すまで」)が入る。過ぎたら無いものとして扱う。ぷちの体の居場所（家 / お外）は、体験デーモンが `characters/<id>/state/experience_state.json` に書く体の Wi-Fi（何番目か）から決める。どの番号がどこかは `PETIT_DATA_DIR/config/places.json`（無ければ 1・2 = 家、3 = お外）。計算と保存は `scripts/whereabouts.py`。会話の system prompt と自律行動の冒頭に「ありさんのいま: 会社(9:02 から)」「あなたの体のいま: 家(家の Wi-Fi)」と伝わる |
| `anniversaries.html` | 記念日（`/anniversaries`）。家の設定 `PETIT_DATA_DIR/config/anniversaries.json` に、名前・最初の日・くり返し（毎年・毎月・その日だけ）・ひとことを足す。計算と保存は `scripts/anniversaries.py`。当日は、ぷちログのその日のいちばん上に出る。ぷちたちには、前の日の自律行動で 1 回だけ「あしたは○○の日」と伝わる（`anniversaries.py notice`。前の日に動かなかった子には当日に）。ぷちも `anniversaries.py add` で足せる |
| `desires.html` | 欲求の様子（`/desires`）。その子の欲求ごとに、この数日の強さの線・上限にいた時間・いちばん強かった時間・満たした記憶の回数と、その欲求の決まり（満たすまでの時間・満たしたことになる言葉）を出す。データの組み立ては `dashboard/desire_history.py`（読むだけ） |
| `styleguide.html` | 部品の見本（`/ui`） |

Web フォント・markdown の変換・会話の画像化は、外の CDN（Google Fonts・jsDelivr）から部品を読む。届かないときは、端末のフォントと素の文字で出る。

## ぷちに渡す文(2026-11-13)

会話の system prompt、写真・声の前置き、来場者、ぷち同士、体のイベント(カメラ・センサー・マイク)、展示の一言、日記の文は `prompts/dashboard/*.md`(一覧は `prompts/README.md`)。`main.py` は `_prompt("<名前>", **値)` で組み立てるだけで日本語の文を持たない。
家ごとの言い回しは `PETIT_DATA_DIR/prompts/dashboard/<同名>.md` を置けば上書き(ダッシュボードの再起動は不要。毎回読む)。展示用の固定の紹介文は `prompts/dashboard/display_char_info.json`(同じく家で上書き可)。

