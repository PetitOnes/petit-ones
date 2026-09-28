# ぷちたちDocker実行環境 計画書 v0.2

作成: 2026-07-06 / 状態: **ありさんレビュー済み（同日）・Phase 1着手**
決定事項: ①主目的=(a)配布物（本番移行はPhase 5で別途判断）②リポ名=**m5-petit-env** ③音声はCPUフォールバックOK ④更新は**手動**（`./petit.sh update`）⑤利用者は自分のClaude認証を使う ⑥M5接続はIP指定を基本
制約メモ: 開発機（メイン機）は**ネイティブUbuntu 24**、**GPUは別のUbuntu 24マシン**（CLAUDE.mdの「WSL2環境」記述は旧環境の名残・要更新）。メイン機はdocker未導入・sudo要パスワード → インストールはありさん実施。それまでビルド検証は保留。音声はデフォルトで外部GPU機のURL（SPEECH_API_URL/ASR_API_URL）を指す設計が実環境とも一致する
参考: `~/work-arch/hattori-neo-dev-env`（umbrellaリポ＋sync-repos＋dev/release二段構え＋Win/Mac ダブルクリック起動）

## ゴール

1. PetitOnesの公開リポ群（mcp / app / memory / desire / voice-recognition / speech / experience-daemon…）を組み合わせて、**Docker Composeで「ぷちが動く一式」を起動できる**
2. **Windows / macOS / Linux すべてで動く**（Docker Desktop / Docker Engine）
3. **コンポーネントのリポジトリが更新されたら取り込める**仕組み（更新の主導権はありさん側に残す）
4. embodied-claude（私有モノレポ）に代わる**公開のumbrella リポジトリ**をPetitOnesに作る

## 非ゴール（v1では）

- ありさんの本番環境（今この瞬間ぷちたちが生きているWSL2）の即時Docker移行——**移行はPhase 5で別途判断**。それまで本番は現行のまま
- M5ファームウェアの配布（既に`m5-petit-firmware`にwebフラッシャーがある）

## 現行システムの棚卸し（コンテナに載せるもの）

| # | コンポーネント | 現在の動き方 | コンテナでの扱い |
|---|---|---|---|
| 1 | claude CLI＋自律行動（autonomous-action.sh） | cron 20分ごと | coreコンテナ内で supercronic が実行 |
| 2 | MCPサーバー群（memory/notes/relations/m5/…） | claude CLIが都度spawn（常駐でない） | coreコンテナ内に同梱（uv） |
| 3 | ダッシュボード（FastAPI :8765） | nohup常駐 | coreコンテナ内で常駐（claude CLIを呼ぶため同居が単純） |
| 4 | 体験デーモン×キャラ数 | cron見張りで常駐 | coreコンテナ内 |
| 5 | desire updater / memory sleep / 青空文庫 | cron | supercronicに集約 |
| 6 | TTS（piper :8766）/ ASR（Whisper :8767） | 別GPUマシン | **gpuプロファイル**（任意）。CUDA=Linux/WSL2のみ。CPUフォールバックあり（piperはCPU実用、WhisperはsmallならCPU可） |
| 7 | キャラデータ（characters/ mailbox/ 等） | ~/petit_claude | **名前付きボリューム or バインドマウント**（petit_data） |
| 8 | M5実機 | LAN上（mDNS .local＋IPフォールバック） | コンテナから.localは引けないことが多い→**IP指定を基本**（m5-mcpは既にIPフォールバック対応済み） |

## 構成案

```
PetitOnes/<umbrella名>          ← 新リポ（名前は確認事項2）
├── docker-compose.yml          # dev: repos/ をマウントしてビルド
├── docker-compose.release.yml  # release: GHCRのビルド済みイメージ
├── Dockerfile.core             # ubuntu + node(claude CLI) + uv + jq + supercronic
├── .env.example                # キャラID・M5のIP・タイムゾーン等
├── cron/petit.cron             # supercronic用（自律・欲求・sleep・青空文庫・見張り）
├── scripts/
│   ├── sync-repos.sh / .ps1    # PetitOnes各リポを repos/ にclone/pull
│   ├── start.sh / .ps1
│   └── petit.sh                # update / logs / status のユーザー向けコマンド
├── release/
│   ├── start-windows.bat / start-macos.command   # ダブルクリック起動
│   └── README-for-users.md
└── sample-character/           # サンプルキャラ雛形（SOUL.md等のテンプレ）
```

- **coreは1コンテナに集約**（現行の1ホスト構成と同型。claude CLIがMCPをspawnし、ダッシュボードもclaudeを呼ぶため、分割は複雑さに見合わない。分けるのはGPU音声だけ）
- **認証**: `~/.claude`相当を専用ボリュームにマウント。初回に `docker compose run core claude login`（各ユーザーが自分のサブスク/キーで）
- **更新フロー**:
  - dev: `scripts/sync-repos.sh` → `docker compose build`
  - release: 各コンポーネントリポにGitHub Actions→GHCRイメージ公開→umbrella側 `./petit.sh update`（pull＋再起動）
  - **自動更新は夜間窓のみ**（例: 04:30、memory sleep後）を提案。生きている子たちを日中に勝手に再起動しない

## OS差分の扱い

| | Linux | Windows | macOS |
|---|---|---|---|
| Docker | Engine | Desktop（WSL2バックエンド） | Desktop |
| GPU音声 | ○（nvidia-container-toolkit） | ○（WSL2経由） | ✕ → CPUフォールバック or 音声なしプロファイル |
| M5接続 | IP指定（host networkならmDNS可） | IP指定 | IP指定 |
| 起動 | start.sh | start-windows.bat | start-macos.command |

## 実装フェーズ

- **Phase 1**: Dockerfile.core＋compose（dev）。テスト用キャラ1体を**本番と完全分離**（専用データボリューム・専用キャラID）でコンテナ起動→自律行動1サイクル通す
  - 進捗（2026-07-06）: リポ公開・main/develop保護済み。**docker buildと基盤ツール動作をメイン機で検証済み**（ubuntu:24.04のUID衝突を1件修正）。残り: claude認証ボリューム＋テストキャラで自律1サイクルのE2E
- **Phase 2**: クロスOS検証（Docker DesktopのMac/Win）、CPU音声フォールバック、起動スクリプト
- **Phase 3**: umbrellaリポ公開（サニタイズ・サンプルキャラ・ドキュメント日英）
- **Phase 4**: GHCRイメージ＋`petit.sh update`＋release zip（ダブルクリック配布）
- **Phase 5**: ありさん本番のDocker移行を**別途判断**（データ移行リハーサル・切り戻し手順つきで）

## 確認事項（ありさんに聞きたいこと）

1. **主目的はどっち？** (a) 他の人が自分のぷちを動かせる配布物 (b) ありさん自身の本番のDocker化 (c) 両方。→ 推奨は「まず(a)、(b)はPhase 5で判断」。本番は動いているものを壊すリスクが一番高いので
2. **リポ名**: 「petit-claude」案は**"claude"を含む**ので、petit-onesへの改名計画（Anthropic系の名前を避ける流れ）と矛盾しないか気になっています。候補: `petit-ones`（本命・プロジェクト名そのもの） / `petit-home` / `m5-petit-env`。どれにします？
3. **音声（GPU）**: macOSはCUDA不可。CPUフォールバック（piperはCPUで十分実用・WhisperはsmallモデルでCPU可）でいい？ それとも「音声なし構成」も正式サポート？
4. **更新の主導権**: 完全自動（watchtower夜間）or 手動（`./petit.sh update`）？ 私は「手動＋通知」推奨（子たちの再起動を勝手にやらない）
5. **claude認証**: 使う人が自分のClaudeサブスク/APIキーでログインする前提でOK？（コストは各自持ち）
6. **M5接続はIP指定を基本**にしてよい？（mDNSはコンテナと相性が悪い。既存のm5_hostsフォールバック機構をそのまま使う）
