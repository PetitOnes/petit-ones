# memory-mcp / desire-system 公開リポジトリ切り出し計画

作成: 2026-07-06 / 状態: Sonnetサブエージェントが実行中
承認: ありさん（2026-07-06、リポ名・public公開とも承認済み）

## 対象と行き先

| 元（embodied-claude内） | 新リポジトリ | 公開 |
|---|---|---|
| `memory-mcp/` | `PetitOnes/m5-petit-memory` | public |
| `desire-system/` | `PetitOnes/m5-petit-desire` | public |

既存のm5-petit-*シリーズ（mcp / app / speech / firmware / scripts / setup）に続く7・8個目。

## 方針

1. **元ディレクトリは無変更**。本番稼働中（cron・自律行動が使用）。コピーで作業
2. **git履歴は持ち込まない**。新規initの1コミット目から（過去コミットへの個人情報混入リスクを丸ごと回避。他のm5-petit-*と同じやり方）
3. **データは絶対に含めない**: *.db、記憶データ、.env、__pycache__、.venv。コードと設定例のみ
4. **サニタイズ**: `/home/cube-petit`等の絶対パス→環境変数化、メール・トークン・キャラ固有値のgrepをゼロ件にしてからpush
5. **流儀合わせ**: 日英併記description、README（セットアップ・環境変数一覧・MCP設定例）、既存リポのLICENSEに合わせる
6. **mainブランチ保護**: petit-personaと同じ（force push禁止・削除禁止・enforce_admins）

## 運用（切り出し後）

- **当面: embodied-claude内の現物が本番**。公開リポはそのスナップショット。ぷちたちの生活への影響ゼロ
- 変更フロー: embodied-claude側で開発・検証 → 落ち着いたタイミングで公開リポへ反映（手動同期）
- 将来、公開リポを本体に切り替えるか（embodied-claudeからはgit submodule/依存として参照）は、petit-onesプロジェクト名移行（6/15以降の`claude -p`制限対応）と合わせて判断

## 切り出し済み・関連リポ一覧（2026-07-06時点）

- `PetitOnes/petit-persona` — PETIT PERSONA診断（GitHub Pages公開: https://petitones.github.io/petit-persona/）
- `PetitOnes/m5-petit-memory` — **完了**（Apache-2.0、194テスト通過、ブランチ保護済み）
- `PetitOnes/m5-petit-desire` — **完了**（Apache-2.0、42テスト通過、ブランチ保護済み）
- `PetitOnes/m5-petit-voice-recognition` — **完了**（`~/work/m5_petit_gpu_server/m5_petit_voice_recognition` から。Apache-2.0、ブランチ保護済み）
  - 発見: `m5-petit-speech` は実はTTS＋voice-recognition両方入りのモノレポだった（過去の移植の名残）。重複整理（speech側からvoice-recognitionサブディレクトリを消すか）はありさん判断待ち
- `PetitOnes/m5-petit-relations` — **完了**（`relations-mcp/` から。上流embodied-claudeには存在しないオリジナルコンポーネントのためNOTICE不要。Apache-2.0、ブランチ保護済み。テストスイート未整備のためテストなし、READMEに明記）
  - サニタイズ: docstring中の実キャラ名（`ありさん`/`arisan`）を汎用の`owner`（人間のオーナー）に置換。パスのデフォルトも`~/petit_claude/characters`直書きから`PETIT_DATA_DIR`（デフォルト`~/petit_data`、姉妹リポと共通の慣習）ベースに変更
- `PetitOnes/m5-petit-notes` — **完了**（`notes-mcp/` から。上流embodied-claudeには存在しないオリジナルコンポーネントのためNOTICE不要。Apache-2.0、16テスト通過、ブランチ保護済み、topics設定済み）
  - サニタイズ: `CHARACTER_ID`のデフォルト値`puchiko`（実キャラ名ハードコード）を`default`に置換。`PETIT_DATA_DIR`のデフォルトも`~/petit_claude`直書きから`~/petit_data`（姉妹リポと共通の慣習）に変更
- `PetitOnes/roman2026` — **完了**（2026-08-09。RO-MAN 2026 LBR補足ページ。GitHub Pages公開: https://petitones.github.io/roman2026/ 。論文PDF・ポスターPDF・システム紹介。コンポーネント切り出しではないためキャラ名＝論文公表済みの主題はサニタイズ対象外、パス・秘密情報はgrepゼロ件確認。Apache-2.0（PDF・写真は著者著作権）、main/developブランチ保護済み、topics設定済み）

## 切り出しで見つかった注意点（2026-07-06）

- **gitコミット名義の漏れ（ありさん指摘）**: このマシンのグローバルgit設定（AiriYokochi＋仕事用メール）が公開リポのコミットに乗っていた。全13リポをgit filter-repo（mailmap）で `RRYZ09 <airi.yokochi.3@gmail.com>` に書き換え済み（保護一時解除→強制push→再適用）。**今後は必ずコミット前に `git config user.name "RRYZ09"` / `user.email "225634165+RRYZ09@users.noreply.github.com"` をローカル設定**（スキルにも追記済み）

- **上流ライセンスの帰属義務（ありさん指摘）**: memory-mcp・desire-systemは `lifemate-ai/embodied-claude`（MIT）由来。MITは元の著作権表示・ライセンス文の保持が義務。両リポにNOTICE（上流MIT全文＋帰属）とREADMEクレジットを追加して対応済み（Apache-2.0のままMITコード取り込みは適法）。**今後の切り出しでは必ず「上流に同名コンポーネントがあるか」を確認し、あればNOTICEを最初から入れること**

- desire-systemの`.env`に実データ（COMPANION_NAME=ありさん）が残っていた→公開版から除外済み。**他コンポーネント切り出し時も.envの実データ残存に注意**
- memory-mcpのREADMEに実装と乖離した記述（e5-small表記、存在しないファイル名）→公開版で修正済み。**embodied-claude側のREADMEは古いまま**（直すなら別途）
- 公開版はデータディレクトリのデフォルトを `~/petit_data` に統一（姉妹リポの慣習）。embodied-claude側は `~/petit_claude` のままで互換影響なし

## 完了（2026-07-06）

embodied-claude内の全MCPサーバー（mcp / memory / desire / notes / relations）の公開が完了。m5-petit-envのsync-reposが依存する全コンポーネントが揃った。

## 残タスク

- [x] 成果物レビュー（サニタイズ一覧の確認）
- [ ] embodied-claude の README / CLAUDE.md に公開リポへの参照を追記
- [ ] 実機でのフルインストール検証（m5-petit-memoryのuv.lockはtorch 2.12.1/CUDA。本番は2.10.0のため、新規展開時に要確認）
- [ ] m5-petit-envのsync-reposスクリプトが notes/relations も引くよう更新（作成時点では未公開だったため対象外だった）
