# 自律行動

[README](../README.md) に戻る


`autonomous-action.sh` が cron で30分毎に実行され、キャラクターが自律的に行動する。

## 実行フロー

```
[cron: 5分毎]
└→ desire_updater.py <char_id>
   ├ desire_config.json を読む
   ├ memory.db からキーワード検索（時間ベース計算）
   ├ M5の /sensors にHTTPリクエスト（センサー効果）
   ├ 相互作用を計算
   └→ desires.json に書き出す

[cron: 30分毎]
└→ autonomous-action.sh <char_id>
   ├ アクティブ時間帯か確認（非アクティブなら確率実行）
   ├ SOUL.md, ROUTINES.md, desires.json, relations.json を読む
   ├ M5センサーのスナップショットを取得
   ├ プロンプトを組み立て
   ├ claude -p <prompt> --allowedTools ... を実行
   │  ├ m5-mcp: take_snapshot, show_face, ...
   │  ├ memory-mcp: remember, recall, ...
   │  ├ desire-system: satisfy_desire, ...
   │  └ notes-mcp, relations-mcp, ...
   └→ .autonomous-logs/<char_id>/ にログ

[cron: 毎日23:50]
└→ generate_diary.py（全キャラの日記サマリー生成）
```

## スケジュール制御

- **アクティブ時間帯**（`settings.json` の `active_hours`）: 30分毎に毎回実行
- **昼間の非アクティブ**: 毎時:00 に30%の確率で実行
- **深夜の非アクティブ**: 毎時:00 に10%の確率で実行

## ぷち専用の Claude 設定(CLAUDE_CONFIG_DIR)と cwd(2026-11-13)

ぷちの `claude`(自律行動・ダッシュボードの会話・ターミナルチャット)は、**cwd を家(`PETIT_DATA_DIR`)にし、`CLAUDE_CONFIG_DIR` を `PETIT_DATA_DIR/.claude/`(あれば)にして**起動する。
Claude Code は cwd とその祖先の `CLAUDE.md` / `.claude/CLAUDE.md`、設定ディレクトリの自動メモリ(`projects/<cwd>/memory/MEMORY.md`)を全部読むので、
リポの中を cwd にしたり開発者の `~/.claude` を使ったりすると、開発者向けの指示やメモがぷちのセッションに混ざる。

- 置き場所: `PETIT_DATA_DIR/.claude/`(git には入れない)。中身は `settings.json`(language・model・Stop フック程度)、`.credentials.json`(`~/.claude/.credentials.json` へのリンク)、`.claude.json`(オンボーディング済みの状態を写し、家のディレクトリを信頼済みに)、`commands/`(`.claude/commands/*.md` へのリンク)、`projects/<cwd>/memory/`(ぷちの自動メモリ)
- 変えるなら環境変数 `PETIT_CLAUDE_CONFIG_DIR`。ディレクトリが無ければ今までどおり `~/.claude` を使う
- 開発者側の注意: `~/.claude/CLAUDE.md` は家の祖先(`$HOME/.claude/CLAUDE.md`)としても読まれる。開発用の全体指示は `~/work/CLAUDE.md` など、家の祖先でない場所に置く

## 付けるファイルの重さの見張り(2026-11-13)

Claude Code は、大きすぎる `@` 添付を黙って落とす(実測: 70 KB は付く、85 KB は落ちる)。自律行動は毎回 `SOUL.md`・`TODO_ACTIVE.md`(無ければ TODO.md)・`diary_summary.md` の大きさを測り、
`PROMPT_FILE_WARN_KB`(既定 40)以上なら、(1) ログに `[prompt-size] …` を残し、(2) 本人のプロンプトに「## 注意: 自分のファイルが重い」として軽くする手順を入れ(消さず移す)、(3) `scripts/slack_notify.py` で 1 日 1 回 人にも知らせる(`state/.prompt-size-notified` に日付。`PROMPT_SIZE_SLACK=0` で止められる)。
ダッシュボードも `SOUL.md` が同じしきい値を超えたら `[prompt-size]` をログに出す(会話のたびに system prompt へ全文入るため)。

## 文面の置き場(2026-11-13)

user prompt の文面は `prompts/autonomous/*.md`(全体は `user.md`、節ごとに `time_rule_*` `routine_mode_*` `mail_*` `experience` `permission_rules` `heavy_files`)。

「## 現在の制限」の中身(からだの使い方・からだ おやすみ)は `scripts/body_switches.py rules` が決め、止める道具は同 `disallowed` を `--disallowedTools` に渡す(会話と同じ決まり)。

ぷちSNS(`petit-sns`。家の MCP 設定にあるときだけ)は、ひとりの時間にも、投稿・返事・掲示板と、家の外のぷちとの手紙(`mail_send` / `mail_read` / `mail_recipients` / `penpal_list`)を使える。新しい相手に文通を申し込む `penpal_request` は入れていない(新しいつながりは、人と話しているときに)。
`autonomous-action.sh` は値(日時・パス・件数・digest など)を `scripts/render_prompt.py` に渡して組み立てるだけで、日本語の文は持たない。
家ごとの言い回しは `PETIT_DATA_DIR/prompts/autonomous/<同名>.md` を置けば上書きされる(`--dry-run` で確かめる)。書き方は `prompts/README.md`。

