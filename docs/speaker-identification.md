# 話者認識

[README](../README.md) に戻る


M5Stack のマイクで録音した音声が「誰の声か」をリアルタイムで識別する機能。GPU サーバー上の [resemblyzer](https://github.com/resemble-ai/Resemblyzer) を使い、声紋（話者埋め込み）で照合する。

## 仕組み

```
[M5 MIC] → [WAV] → [GPU サーバー /analyze_audio_summary]
                          ↓
                   resemblyzer で声紋照合
                   → speaker: "arisan" (confidence: 0.87)
                          ↓
                   Claude のプロンプトに「ありさんの声」として渡る
```

## GPU サーバーのセットアップ

[m5_petit_gpu_server](https://github.com/AiriYokochi/m5_petit_gpu_server) リポジトリで:

```bash
git pull
uv sync   # resemblyzer が追加されている
# サーバー再起動
```

## 話者の登録方法

### 1. speaker_config.json を作成

```bash
cp scripts/speaker_config.json.example ~/petit_claude/speaker_config.json
vim ~/petit_claude/speaker_config.json
```

```json
{
  "my_speaker_id": "arisan",
  "my_username": "arisan"
}
```

- `my_speaker_id`: あなたの話者ID（GPU サーバーの声紋DBに保存されるキー）
- `my_username`: ダッシュボードのログインユーザー名（`auth.json` と一致させる）

### 2. 登録スクリプトを実行

```bash
# 自分の声を登録（speaker_config.json から読む）
./scripts/register_speaker.sh

# 他の人の声を登録（引数で指定）
./scripts/register_speaker.sh kazahaya puchiteya

# 別のM5を使う
./scripts/register_speaker.sh arisan puchiko
```

### 3. M5 のMICボタンを押して話す

スクリプトが「✓ 準備完了」と表示したら、指定したキャラクターのM5の **MICボタンを押して10〜20秒話す**。

無音5秒で自動的に録音が終わり、声紋が GPU サーバーに登録される。

**精度を上げるには**: 同じスクリプトをもう一度実行して別の内容を話す（3〜5回推奨）。声紋は毎回インクリメンタルに平均化される。

### ぷちたちの TTS 声紋を自動登録

ぷちたちは実際にマイクで話す代わりに、各自の TTS 設定（`~/petit_claude/characters/{char_id}/voice_settings.json`）から音声を生成して登録できる。

```bash
# 3キャラ分まとめて登録（各3テキストで移動平均）
python3 scripts/register_tts_voices.py

# 特定キャラだけ再登録
python3 scripts/register_tts_voices.py --chars puchiteya

# URL を明示する場合
python3 scripts/register_tts_voices.py --tts-url http://puchipuchi:8766 --asr-url http://puchipuchi:8765
```

TTS の声を変えた（`set_voice` を呼んだ）場合は再実行して声紋を更新する。

### 登録状況の確認・削除

```bash
# 登録済み話者一覧
curl http://puchipuchi:8765/speakers

# 話者を削除
curl -X DELETE http://puchipuchi:8765/speakers/kazahaya
```

## 対応する話者ID

| ID | 説明 |
|----|------|
| `arisan` | ありさん |
| `puchiteya` | ぷちてゃ |
| `puchiko` | ぷちこ |
| `puchiru` | ぷちる |
| その他 | 自由に追加可 |

登録されていない声は `"unknown"` として扱われる（閾値: コサイン類似度 0.75）。

## 声紋DBの場所

GPU サーバー側の `speaker_registry.json`（`SPEAKER_REGISTRY_PATH` 環境変数で変更可）。DB は全キャラ（全M5）で共有されるため、1台のM5で登録すれば他の全キャラが認識できる。
