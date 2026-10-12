# MCP サーバー

[README](../README.md) に戻る


## m5-mcp（目・感情・センサー）

M5Stack のファームウェアセットアップは [m5_petit](https://github.com/AiriYokochi/m5_petit) を参照。IP は環境変数 `M5_HOST` で指定（`autonomous-mcp.json` から渡される）。

音声認識（ASR）と TTS は GPU サーバーが担当する。[m5_petit_gpu_server](https://github.com/AiriYokochi/m5_petit_gpu_server) をセットアップし、`VOICE_API_HOST` 環境変数にそのホスト名/IPを設定する（デフォルト: `puchipuchi`）。

| ツール | 説明 |
|--------|------|
| `take_snapshot` | M5カメラで撮影 |
| `look` | 視線を動かす (x/y: -100〜100) |
| `blink` | ウィンクする |
| `show_face` | 顔画像を表示（SDカードのJPEG） |
| `play_sound` | 効果音を再生 |
| `play_icon` | アイコンを表示（love / cry） |
| `get_sensor_data` | 近接・照度・加速度・ジャイロ・バッテリー取得 |
| `wait_for_touch` | タッチイベント待機 |
| `wait_for_menu_select` | タッチメニューの選択イベント待機（camera/sensor/mic） |
| `set_volume` / `get_volume` | 音量設定 |
| `sleep` / `wake` | スリープ制御 |
| `save_to_album` | スナップショットを撮ってアルバムに保存 |
| `list_album` | アルバム一覧取得（`unread_by` で未読フィルタ可） |
| `view_album_photo` | アルバムの写真を取得＋既読記録 |
| `delete_album_photo` | 自分のアルバムから写真を削除（`CHARACTER_ID`で自キャラのみ） |
| `lock_album_photo` | 写真をロック/解除トグル（ロック中は自動削除スキップ） |
| `speak` | VOICEVOX/kokoro/piper でTTS合成してM5で再生。`save_as_memo=True` でボイスメモにも保存 |
| `set_voice` | 自分のTTS声設定を保存（speaker/speed/pitch/intonation/volume）|
| `list_voice_memos` | ボイスメモ一覧取得。`unlistened_by` で未聴フィルタ可 |
| `listen_voice_memo` | ボイスメモをM5で再生し既聴記録。`transcribe=True` で文字起こし |
| `lock_voice_memo` | ボイスメモのロック/解除トグル（ロック中は自動削除スキップ） |

> `delete_album_photo` は `autonomous-mcp.json` の m5-mcp env に `CHARACTER_ID` が設定されている場合のみ動作する。他キャラのアルバムは削除不可。

### TTS 声設定

各キャラの声設定は `~/petit_claude/characters/{char_id}/voice_settings.json` に保存される。`set_voice` ツールで更新し、`speak` はこの設定を自動で読んで使う。

```json
{
  "voicevox_speaker": 23,
  "speed_scale": 1.0,
  "pitch_scale": 0.05,
  "intonation_scale": 1.2,
  "volume_scale": 1.0
}
```

声設定を変えたあとは `python3 scripts/register_tts_voices.py` で話者認識の声紋も更新する。

## memory-mcp（記憶）

| ツール | 説明 |
|--------|------|
| `remember` | 記憶を保存（emotion, importance, category 付き） |
| `recall` / `recall_divergent` | 文脈に基づく想起（発散的想起は連想展開付き） |
| `search_memories` | セマンティック検索 |
| `recall_with_associations` | 関連記憶も含めて想起 |
| `save_visual_memory` | 画像 + カメラ角度付き記憶保存 |
| `save_audio_memory` | 音声 + 書き起こし付き記憶保存 |
| `recall_by_camera_position` | カメラの向きで記憶を想起 |
| `create_episode` / `search_episodes` | エピソード管理 |
| `link_memories` / `get_causal_chain` | 因果リンク |
| `get_working_memory` / `refresh_working_memory` | 作業記憶 |
| `consolidate_memories` | 記憶の再生・統合 |
| `sleep` | 記憶整理（圧縮・減衰・忘却） |
| `tom` | Theory of Mind（相手の視点取得） |

## desire-system（欲求）

3段階パイプラインで欲求レベルを計算:

1. **時間ベース**: 記憶DB内のキーワード最終出現時刻からの経過時間
2. **センサー効果**: M5のセンサー値（ambient, gx, battery等）で加減算
3. **相互作用**: 欲求間の影響（例: 疲労が高いと好奇心が下がる）

| ツール | 説明 |
|--------|------|
| `get_desires` | 現在の欲求レベル取得 |
| `satisfy_desire` | 欲求を満たす（行動後に呼ぶ） |
| `boost_desire` | 欲求を刺激する（驚き・発見時） |

欲求の定義・キーワード・センサー効果は `characters/{id}/desire_config.json` でカスタマイズ可能。cron で5分毎に `desire_updater.py` がレベルを再計算し `desires.json` に書き出す。

## relations-mcp（関係性）

| ツール | 説明 |
|--------|------|
| `get_relations` | 自分と他キャラの関係性を取得 |
| `update_relation` | 関係性情報を更新（好き嫌い・親密度・メモ） |

## notes-mcp（ノート）

| ツール | 説明 |
|--------|------|
| `list_notes` | ノート一覧 |
| `read_note` | ノート読み取り |
| `write_note` | ノート作成・更新 |

記憶 (memory) と違い、検索・想起の対象にならない永続的な参照ドキュメント。光の値メモ、センサー範囲表などに使う。
