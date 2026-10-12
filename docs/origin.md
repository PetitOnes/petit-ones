# 出発点との違い

[README](../README.md) に戻る


[kmizu/embodied-claude](https://github.com/kmizu/embodied-claude) は「Claude に身体を与える」MCP サーバー群。Wi-Fi PTZ カメラ・USB カメラ・TTS・長期記憶・温度センサーなどのモジュールで、単一の Claude インスタンスに感覚を提供する。

petit-ones は、そのコンセプトを**マルチキャラクター自律エージェント**へ拡張したもの。

## 主な違い

| | 出発点 (kmizu) | petit-ones |
|---|---|---|
| **ハードウェア** | Wi-Fi PTZ カメラ (Tapo C210等) | M5Stack CoreS3 |
| **キャラクター** | 単一インスタンス | 複数キャラ（独立した性格・記憶・欲求） |
| **自律性** | ユーザー主導（リアクティブ） | cron で30分毎に自律行動（欲求ベース） |
| **欲求** | オプション | 中核機能（sensor_effects, cross_effects） |
| **UI** | CLI のみ | Web ダッシュボード（チャット・欲求表示・日記・記憶閲覧） |
| **社会性** | なし | キャラ同士の関係性・メールボックス |
| **携帯性** | 据え置き | M5Stack + モバイルバッテリーで外出可能 |

## 追加コンポーネント

| コンポーネント | 説明 |
|---|---|
| **m5-mcp** | M5Stack 制御（カメラ・顔・センサー・音・スリープ）。wifi-cam-mcp/usb-webcam-mcp に代わるもの |
| **GPU サーバー** | 音声認識（Whisper ASR, port 8765）・TTS（port 8766）を担当。別リポジトリ [m5_petit_gpu_server](https://github.com/AiriYokochi/m5_petit_gpu_server) を参照 |
| **desire-system** | 欲求システム。時間経過 + センサー + 相互作用の3段階で欲求レベルを計算 |
| **relations-mcp** | キャラ間の関係性（好き嫌い・親密度・メモ） |
| **notes-mcp** | 永続ノート（光の値メモ、センサー範囲表など） |
| **dashboard** | Web UI（チャット・グループチャット・欲求表示・記憶閲覧・日記・認証） |
| **create_character.py** | キャラクター追加スクリプト（設定ファイル + cron 自動登録） |
| **autonomous-action.sh** | 自律行動オーケストレーション（スケジュール・確率制御・セッション管理） |
| **scripts/** | メールボックス書き込み (`write_mailbox.py`)、チャットログ保存 (`append_chat_log.py`)、バックアップ/復元 (`backup_petit.sh` / `restore_petit.sh`)、メモリ読み出し (`reader.py`) |

## フォーク元から引き継いでいるもの

memory-mcp はフォーク元にも存在する。このフォークでは視覚記憶・エピソード・因果リンク・Theory of Mind・記憶整理 (sleep) などが追加されている。wifi-cam-mcp, usb-webcam-mcp, system-temperature-mcp, ip-webcam-mcp, mcp-pet, mobility-mcp, morning-call-mcp は `archive/` に退避済み（未使用）。
