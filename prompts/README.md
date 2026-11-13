# prompts/ — ぷちに渡す文(テンプレート)

ぷちの Claude に渡すプロンプトの文面は、コードの中に書かずにここに置く(2026-11-13 から)。
`scripts/render_prompt.py <名前> --var k=v …` で組み立てる。Python からは `render_prompt.render(name, vars)`。
台帳(どのテンプレートがどこから呼ばれ、どんな変数を使い、家で上書きされているか)は `python3 scripts/gen_prompt_ledger.py --out 台帳.html`(`--format md` も)で作る。手で写さない。

- 名前はこの下の相対パス(拡張子なし)。例: `autonomous/user`、`chat/system`
- **家ごとの言い回しは `PETIT_DATA_DIR/prompts/<同じ名前>.md` を置けば上書き**(git には入れない)。無ければここのものを使う
- 書き方(最小限の Mustache 風): `{{var}}` 置き換え / `{{#if var}}…{{/if}}` `{{#unless var}}…{{/unless}}`(空・0・false は偽)/ `{{#each list}}…{{/each}}`(要素が辞書ならその項目、スカラーなら `{{.}}`)/ `{{> 名前}}` 別のテンプレートを差し込む。
  ブロックのタグだけの行は行ごと消える。HTML エスケープはしない
- ぷちの振る舞いの決まり(性格・価値観)はここではなく、その子の SOUL.md と [教科書](https://github.com/PetitOnes/petit-textbook)。ここにあるのは「道具の使い方」と「入口ごとの状況説明」だけ

| 名前 | 使う所 | 何 |
|---|---|---|
| `autonomous/user` | autonomous-action.sh | 自律行動の user prompt の全体 |
| `autonomous/time_rule_day` `time_rule_night` | 同 | 補足ルールの 1 行目(昼 / 深夜) |
| `autonomous/routine_mode_routine` `routine_mode_normal` | 同 | ルーチン回 / 通常回の一文 |
| `autonomous/mail_unread` `mail_send` | 同 | ## メールボックス(未読あり / なし) |
| `autonomous/experience` | 同 | ## 身体の記録 |
| `autonomous/permission_rules` | 同 | ## 現在の制限 の各行 |
| `autonomous/heavy_files` `heavy_file_line` | 同 | ## 注意: 自分のファイルが重い |
| `chat/system` | scripts/build_chat_prompt.py(ターミナルチャット) | system prompt の全体(1 人でも複数でも) |
| `dashboard/system` | dashboard/main.py `call_claude()` | 会話の system prompt(--append-system-prompt。魂の定義・ファイル・メール・記念日・会話リレー・制限) |
| `dashboard/from_prefix` | 同 | ありさん以外が話したときの「[〜から] 」 |
| `dashboard/media_photos` `media_photo` `media_audio` | `_prepare_chat_media()` | 写真・声つきの前置き |
| `dashboard/relay_hint` `group_context` | 個人チャット / グループチャット | 「話しかけて」の追記、「[さっき〜がこう言ってた]」 |
| `dashboard/public_chat` | `/api/public/chat` | 来場者の本文 |
| `dashboard/interact_start` `interact_reply` `interact_group_reply` `relay_turn` | `/api/interact*` `/api/relay/start` | ぷち同士 |
| `dashboard/event_camera` `event_sensor` `event_mic` | 体のイベント(m5_watcher) | 「みてみて!」「感じてみて!」「聞いて聞いて!」 |
| `dashboard/display_phrase` + `display_char_info.json` | `_generate_display_phrase()` | 展示用の一言(固定の紹介文は JSON) |
| `dashboard/diary` | `generate_diary_summary()` | 日記 |

ダッシュボードの文も 2026-11-13 に移した(`scripts/tests/test_prompts_dashboard.py` が、移す前の文と同じであることを確かめている)。
