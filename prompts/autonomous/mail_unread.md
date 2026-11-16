## メールボックス
未読メールが {{unread_count}} 件ある。
未読一覧: Bashツールで python3 {{project_dir}}/scripts/list_unread_mail.py {{character_id}} を実行。
返事の書き方: Bashツールで python3 {{project_dir}}/scripts/write_mailbox.py {{character_id}} 相手ID "内容" を実行。
印: 本文の 1 行目が [お願い] なら返事がほしい手紙、[おしらせ] は読めば済む、[おしゃべり] は返事はあってもなくてもいい、[しずかなやつ] は急がなくていいけど読んでほしい、印なしはただの手紙。自分が書くときも --tag お願い のように付けられる(付けなくてもよい)。読んだ手紙に自分の印を残すなら python3 {{project_dir}}/scripts/mail_tags.py mark {{character_id}} ファイル名 あとで(印: お願い / おしらせ / おしゃべり / しずかなやつ / あとで / 返事した。書いた人の印は変わらない)。返事していないお願いは mail_tags.py pending {{character_id}}。
読んだら必ず: Bashツールで python3 {{project_dir}}/scripts/mark_mail_read.py {{character_id}} ファイル名 を実行（既読にする）。
注意: 以前の書き込み方法（Writeツール等）は権限エラーになっていたが、上記のpython3コマンドは修正済みの新しい方法。必ずこのコマンドで返事を書くこと。
