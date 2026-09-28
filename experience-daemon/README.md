# experience-daemon（体験デーモン・Phase 1）

M5Stack デバイス（ぷちたちの身体）のセンサーをローカルでポーリングし続け、Claude セッションが
走っていない間の出来事（持ち上げられた・部屋が暗くなった・寝ている間に起こされた 等）を
イベントとして記録するデーモン。**API は一切呼ばない。**

設計書: `../docs/experience-buffer-design.md`

## コンポーネント

| ファイル | 役割 |
|---|---|
| `experienced.py` | デーモン本体。`/sensors` `/status` を約0.5秒間隔でポーリングし、イベントをJSONLに追記 |
| `detectors.py` | イベント検出ロジック（純粋関数/クラス、ネットワーク不使用。テスト容易性のため分離） |
| `experience_digest.py` | 未読イベントを日本語1行ずつに整形して標準出力するCLI |
| `start_experienced.sh` | 起動スクリプト（多重起動防止・setsid nohupでバックグラウンド化） |
| `tests/` | pytest。合成センサー列でイベント検出とダイジェスト整形を検証 |

## 使い方

```bash
# 手動起動（フォアグラウンド、デバッグ用）
uv run python experienced.py --character puchiko

# バックグラウンド起動（多重起動防止つき。既に動いていれば何もしない）
./start_experienced.sh puchiko

# ダイジェスト表示（標準出力。未読ゼロなら何も出さない）
python3 experience_digest.py --character puchiko

# ダイジェスト表示 + カーソルを現在時刻に進める（既読化）
python3 experience_digest.py --character puchiko --mark-read
```

## データの置き場所

`~/petit_claude/characters/<id>/state/` 以下（`PETIT_DATA_DIR` 環境変数で上書き可）:

```
experience/YYYYMMDD.jsonl   # イベントログ（追記のみ、削除しない。研究データにもなる）
experience_cursor           # ダイジェストの既読カーソル（ISO時刻1行）
experience_state.json       # {"state": "awake|asleep|offline", "since": "..."}
```

ホスト解決は `characters/<id>/config/config.json` の `m5_hosts`（配列、フォールバック用）
または `m5_host` を使う。接続できたホストを覚えて次回はそちらを優先する（m5-mcpと同じ流儀）。
デバイスがオフラインでもデーモンはクラッシュせず、ポーリングをリトライし続ける。

## 検出イベント（Phase 1）

| イベント | 検出条件 |
|---|---|
| `picked_up` / `put_down` | 重力ベクトルの向きが25度以上変わる or 加速度分散スパイクが1秒以上継続→`picked_up`。3秒以上静止で`put_down`（`carried_sec`をdetailに） |
| `ambient_jump` | 照度が3倍以上/1/3以下（かつ絶対差50以上）変化し2サンプル以上維持。60秒以内は同種を抑制 |
| `touch` | `lastTouchEventTime`の変化を検知。30秒以内の連続タッチは1件に集約 |
| `offline_gap` | ポーリング失敗が15秒以上続き復帰した時に1件（開始・終了・分数） |
| `sleep` / `woken` | `/status`の`is_sleeping`遷移。true→falseの`woken`は`source:"unknown"`（出典特定はPhase 2） |
| `battery_low` | 電池が20%/10%を下回った時に各1回（+5%回復で再アーム） |

閾値・根拠は `detectors.py` 冒頭の定数コメントを参照。

## 自律行動への注入

`autonomous-action.sh` / `autonomous-action-terminal.sh` が、セッション開始時に
`experience_digest.py --character <id> --mark-read` を呼び、出力があれば
「## 身体の記録（前回目覚めてから）」節としてプロンプトに含める。
デーモン未稼働・スクリプト不在でも自律行動が壊れないよう `2>/dev/null || true` でガードしている。

## crontab への追加（提案・未反映）

このリポジトリからは crontab を直接編集しない。以下を手動で `crontab -e` に追加すること
（設計書の「起動方式」節: @reboot + 5分ごとの見張り）。

```cron
# 体験デーモン（puchiko）: 再起動時に自動起動 + 5分ごとに死んでいたら再起動
@reboot /home/cube-petit/work/embodied-claude/experience-daemon/start_experienced.sh puchiko
*/5 * * * * /home/cube-petit/work/embodied-claude/experience-daemon/start_experienced.sh puchiko
```

puchiteya / puchiru も試験運用が済んだら同様に1行ずつ追加する（キャラごとに1プロセス、障害分離のため）。

## テスト

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest -v
```

## Phase 1 で「やらない」こと（設計書のPhase 2/3）

- sleep/wake/wokenの出典特定（choke point計装、`source`は常に`"unknown"`）
- `vibration_sustained`（周期振動・電車推定）
- マイク・音声
- `asleep_actuation`（寝ている間の顔変更・speak記録）
- ダッシュボード（`call_claude`）・ターミナルチャットhookへの注入（`dashboard/main.py`は未変更）
