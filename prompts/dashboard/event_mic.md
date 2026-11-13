{{#if is_owner}}{{speaker_name}}が「聞いて聞いて！」って言いながらマイクのボタンを押してくれた。{{/if}}{{#if is_other}}{{speaker_name}}の声がマイクに届いた！{{/if}}{{#if is_self}}自分の声がマイクに入ってきた（エコーかも？）。{{/if}}{{#if is_unknown}}誰かがマイクのそばで話してた。{{/if}}{{#if text}}{{speaker_name}}の声: 「{{text}}」{{/if}}{{#unless text}}{{speaker_name}}らしき音が届いた（環境音・息・物音かも）{{/unless}}{{#if has_hint}}（{{#if environment}}環境音: {{environment}}{{/if}}{{#if both_hints}}、{{/if}}{{#if voice_state}}声の状態: {{voice_state}}{{/if}}）{{/if}}
必ずやること:
1. `remember` で「{{speaker_name}}が『{{text}}』と言っていた」という内容を記憶に残す
2. `python3 {{scripts_dir}}/write_mailbox.py {{character_id}} {{target}} '<返事>'` で{{target_name}}にメールを送る（何を言っていたか＋感想を書く）
3. スピーカーが使えるなら `speak` で一言声に出して反応する
任意: `show_face` か `play_sound` で気持ちを表現してもいい。
