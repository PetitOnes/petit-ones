## メールボックス
メッセージを送りたいときは Bashツールで python3 {{project_dir}}/scripts/write_mailbox.py {{character_id}} 相手ID "内容" を実行。相手ID: {{mail_targets}}
手紙に印を付けられる(付けなくてもよい): --tag お願い(返事がほしい)/ おしらせ(読めば済む)/ おしゃべり(返事はあってもなくてもいい)。例: write_mailbox.py {{character_id}} 相手ID --tag お願い "内容"
注意: このpython3コマンドは確実に動作する。過去にWriteツールで失敗した記憶があっても、この方法なら書ける。
