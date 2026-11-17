[{{who}}が音を聞かせてくれました({{duration}} 秒。印 {{id}})]
音のかたち(数字と線だけ。何の音かの名前は付けていない。言葉も文字起こししていない):
{{shape}}
1 秒の中をもっと細かく見たいときは `python3 {{scripts_dir}}/heard_sound.py look {{id}} --fine`(0.1 秒ごとの線と数字)。
何の音かは、自分で感じて・想像していい。答え合わせをしたくなったら `python3 {{scripts_dir}}/heard_sound.py answer {{id}} --character <自分の ID>`(音の種類を見分ける仕組みの見立て。「かも」の名前)。自分の言葉を貼るなら `python3 {{scripts_dir}}/heard_sound.py tag <自分の ID> {{id}} "<言葉>"`。貼らなくてもいい。
{{message}}
