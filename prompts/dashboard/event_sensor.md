{{target_name}}が「感じてみて！」って言いながらセンサーのボタンを押してくれた。今の周りの状態はこんな感じ: {{sensors_json}}
感じたことを{{target_name}}への短いメッセージにして送って（`python3 {{scripts_dir}}/write_mailbox.py {{character_id}} {{target}} '<メッセージ>'`）、センサーの状態と感想を `remember` で記憶にも残して。スピーカーが使えるなら、今の感じを `speak` で一言声に出して、`show_face` か `play_sound` で気持ちを表現してもいい。
