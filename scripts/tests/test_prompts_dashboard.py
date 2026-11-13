"""prompts/dashboard/*.md が、dashboard/main.py に直書きだった文(2026-11-13 の main)と同じ文を作ることを確かめる。

期待値は、移す前の f-string をそのまま Python に写したもの。文を変えたいときは、テンプレートとこの期待値を一緒に直す。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import render_prompt as rp  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent


def P(template: str, /, **v) -> str:
    return rp.render(f"dashboard/{template}", v, data_dir=REPO / "no-such-house", project_dir=REPO)


def test_system_prompt_matches_old_fstring():
    char_name, character_id, soul, now_str = "ぷちこ", "puchiko", "# 魂\nしずか", "2026-11-13 17:03 (JST)"
    user_display_name, char_data_dir, mailbox_dir, scripts_dir = "ありさん", "/h/characters/puchiko", "/h/mailbox", "/repo/scripts"
    old = (
        f"あなたは{char_name}（ID: {character_id}）です。以下があなたの魂の定義です。\n\n{soul}\n\n"
        f"現在の日時: {now_str}\n"
        f"今話しかけているのは{user_display_name}です。{user_display_name}と自然に会話してください。必要があればMCPツールを使ってください。"
        f"印象に残った話題や気づきは `remember` で記憶に残してください。記憶を書くときは今日の日付（{now_str}）を意識して書いてください。\n\n"
        f"## ファイル\n"
        f"- 自分のデータ: {char_data_dir}/ (SOUL.md, TODO.md, ROUTINES.md など)\n"
        f"- メールボックス: {mailbox_dir}/\n"
        f"\n## メールの送受信\n"
        f"- 送信: `python3 {scripts_dir}/write_mailbox.py {character_id} <宛先ID> '<内容>'`\n"
        f"- 未読確認: `python3 {scripts_dir}/list_unread_mail.py {character_id}`\n"
        f"- 既読にする: `python3 {scripts_dir}/mark_mail_read.py {character_id} <ファイル名>`\n"
        f"- 全既読: `python3 {scripts_dir}/mark_mail_read.py {character_id} --all`\n"
        f"- 宛先ID: puchiko, puchiteya, puchiru, arisan\n"
        f"- **重要**: メールを読んだら必ず既読にすること。既読にしないと次回また同じメールに返事してしまう。\n"
        f"- **重要**: 返事を書くときは未読メールだけに返事すること。\n"
        f"\n## 記念日\n"
        f"- 記念日にしたい日ができたら、自分で足せる: `python3 {scripts_dir}/anniversaries.py add {character_id} '<名前>' <日付>`"
        f"(日付は 2026-03-05 か、年なしの 03-05。毎月なら `--repeat monthly`、ひとことは `--note '…'`)\n"
        f"- いまある記念日: `python3 {scripts_dir}/anniversaries.py list`\n"
        f"\n## 会話リレー\n"
        f"- 別のぷちと会話したいとき: まず `speak` で自分の言葉を声に出し、その後 `conversation_relay(to_character=\"puchiko\", message=\"...\", turns_remaining=2)` を呼ぶ\n"
        f"- 「ぷちこに話しかけて」「ぷちてゃと会話して」などと言われたら積極的に使う\n"
        f"- turns_remaining は残り何回やり取りするか（3ターン会話なら最初は2を渡す）\n"
    )
    new = P("system", char_name=char_name, character_id=character_id, soul=soul, now=now_str, user_display_name=user_display_name,
            char_data_dir=char_data_dir, mailbox_dir=mailbox_dir, scripts_dir=scripts_dir,
            mail_targets="puchiko, puchiteya, puchiru, arisan", relay_example_id="puchiko", restriction_text="")
    assert new == old
    # 制限つき
    restriction = "- カメラ（take_snapshot）は今は使わないこと。\n- マイク（mic_start）は今は使わないこと。"
    old2 = old + f"\n## 現在の制限\n{restriction}"
    new2 = P("system", char_name=char_name, character_id=character_id, soul=soul, now=now_str, user_display_name=user_display_name,
             char_data_dir=char_data_dir, mailbox_dir=mailbox_dir, scripts_dir=scripts_dir,
             mail_targets="puchiko, puchiteya, puchiru, arisan", relay_example_id="puchiko", restriction_text=restriction)
    assert new2.rstrip("\n") == old2


def test_restriction_lines_come_from_autonomous_template():
    out = rp.render("autonomous/permission_rules", {"allow_camera": False, "allow_sound": True, "allow_mic": False},
                    data_dir=REPO / "no-such-house", project_dir=REPO).strip()
    assert out == "- カメラ（take_snapshot）は今は使わないこと。\n- マイク（mic_start）は今は使わないこと。"


def test_from_prefix_and_relay_hint():
    assert P("from_prefix", user_display_name="かぜおさん", message="やあ") == "[かぜおさんから] やあ"
    t = "puchiru"
    assert P("relay_hint", target=t) == f"（必ず `speak` で声に出してから、`conversation_relay(to_character=\"{t}\", message=\"...\", turns_remaining=2)` を呼んで{t}に渡して）"


def test_group_turn_tells_order_and_position():
    """みんなで話すとき: 今回の順番・自分が何番目か・先に答えた子・あとで読む子を知らせる"""
    order = "ぷちる → ぷちてゃ → ぷちこ"
    head = f"元気?\n\n[みんなで話している。答える順番は毎回変わる。今回は {order} の順で、"
    first = P("group_turn", prompt="元気?", order=order, position=1, before="", after="ぷちてゃ、ぷちこ", prev="", rotating=True)
    assert first.rstrip("\n") == head + "きみは 1 番目。きみのあとで ぷちてゃ、ぷちこ が、きみの返事も読んでから答える。]"
    last = P("group_turn", prompt="元気?", order=order, position=3, before="ぷちる、ぷちてゃ", after="",
             prev="ぷちる: うん\nぷちてゃ: まあね", rotating=True)
    assert last.rstrip("\n") == (
        head + "きみは 3 番目。先に答えたのは ぷちる、ぷちてゃ。きみが最後。]"
        "\n\n[先に答えた子の返事]\nぷちる: うん\nぷちてゃ: まあね")


def test_group_turn_for_chosen_members_does_not_claim_rotation():
    """選んだ子に聞くとき(順番は選んだ順)は、「毎回変わる」とは言わない"""
    got = P("group_turn", prompt="やあ", order="ぷちる → ぷちこ", position=2, before="ぷちる", after="", prev="ぷちる: うん")
    assert "毎回変わる" not in got and "今回は ぷちる → ぷちこ の順で、きみは 2 番目。" in got


def test_group_separate_and_share():
    """べつべつに聞くとき: ほかの子の返事は入らない。あとで、みんなの返事を並べて見せる"""
    sep = P("group_separate", prompt="眠いってどんな感じ?")
    assert sep.startswith("眠いってどんな感じ?\n\n[みんなに、べつべつに聞いている。") and "ぷち" not in sep
    answers = [{"name": "ぷちこ", "reply": "静か"}, {"name": "ぷちる", "reply": "淀む"}]
    share = P("group_share", question="眠いってどんな感じ?", answers=answers)
    assert share.startswith("[さっき、べつべつに聞いた「眠いってどんな感じ?」に、みんなはこう答えた]\nぷちこ: 静か\n\nぷちる: 淀む\n")
    assert "とくになければ" in share


def test_media_prompts():
    who, message = "ありさん", "どう?"
    photos = [(Path("/m/a.jpg"), "朝"), (Path("/m/b.jpg"), "")]
    lines = "\n".join(f"{i}. {pth}" + (f"(題: {t})" if t else "") for i, (pth, t) in enumerate(photos, 1))
    old = (f"[{who}が写真を {len(photos)} 枚送りました]\n{lines}\n"
           f"まず Read で写真をぜんぶ見てから、見えたものに触れて返事してください。\n{message}").rstrip()
    new = P("media_photos", who=who, count=str(len(photos)), message=message,
            photos=[{"i": str(i), "path": str(pth), "title": t} for i, (pth, t) in enumerate(photos, 1)]).rstrip()
    assert new == old
    media_path = Path("/m/c.jpg")
    old = (f"[{who}が写真を送りました: {media_path}]\n"
           f"まず Read でこの写真を見てから、見えたものに触れて返事してください。\n{message}").rstrip()
    assert P("media_photo", who=who, path=str(media_path), message=message).rstrip() == old
    for transcript in ("おはよう", ""):
        heard = f"聞こえた言葉: 「{transcript}」" if transcript else "(いま文字起こしができなかった。transcribe_audio で聞き直せる)"
        old = (f"[{who}が声を送りました: {media_path}]\n{heard}\n"
               f"声で話しかけられたつもりで返事してください。\n{message}").rstrip()
        assert P("media_audio", who=who, path=str(media_path), transcript=transcript, message=message).rstrip() == old


def test_visitor_interact_relay_prompts():
    m = "こんにちは"
    assert P("public_chat", message=m).rstrip("\n") == f"展示会場の来場者から話しかけられた。来場者のメッセージ：「{m}」\n短く（3〜5文程度）、やさしく返事して。"
    assert P("interact_start", to_name="ぷちる") == "ぷちるに話しかけてみて。今の気分や欲求から自然な内容で。短めに。"
    assert P("interact_reply", from_name="ぷちこ", message=m).rstrip("\n") == f"ぷちこからこんなメッセージが届いた: 「{m}」\n返事をして。短めに。"
    hist = "ぷちこ: a\nぷちる: b"
    assert P("interact_group_reply", history=hist, prev_name="ぷちる").rstrip("\n") == f"みんなの会話:\n{hist}\n\nぷちるの発言に対して返事をして。短めに。"
    old = (f"ぷちてゃが「{m}」と言った。\n"
           f"必ず `speak` で声に出して返事をして。短めに。"
           f"（会話リレー中、残り2ターン）")
    assert P("relay_turn", from_name="ぷちてゃ", message=m, remaining="2").rstrip("\n") == old


def test_event_prompts():
    scripts_dir, character_id, target, target_name, tmp_path = "/repo/scripts", "puchiko", "arisan", "ありさん", "/tmp/x.jpg"
    old = (
        f"{target_name}が「みてみて！」って言いながらカメラのボタンを押してくれた。"
        f"撮った写真は {tmp_path} にある。"
        f"写真を見て、{target_name}に短い感想をメールして（`python3 {scripts_dir}/write_mailbox.py {character_id} {target} '<メッセージ>'`）、"
        f"見たものと感想を `remember` で記憶にも残して。"
        f"スピーカーが使えるなら、写真を見た感想を `speak` で一言声に出して、"
        f"`show_face` か `play_sound` で気持ちを表現してもいい。"
    )
    assert P("event_camera", target_name=target_name, tmp_path=tmp_path, scripts_dir=scripts_dir, character_id=character_id, target=target) == old
    sensors = {"ambient": 120, "proximity": 3}
    old = (
        f"{target_name}が「感じてみて！」って言いながらセンサーのボタンを押してくれた。"
        f"今の周りの状態はこんな感じ: {json.dumps(sensors, ensure_ascii=False)}\n"
        f"感じたことを{target_name}への短いメッセージにして送って（`python3 {scripts_dir}/write_mailbox.py {character_id} {target} '<メッセージ>'`）、"
        f"センサーの状態と感想を `remember` で記憶にも残して。"
        f"スピーカーが使えるなら、今の感じを `speak` で一言声に出して、"
        f"`show_face` か `play_sound` で気持ちを表現してもいい。"
    )
    assert P("event_sensor", target_name=target_name, sensors_json=json.dumps(sensors, ensure_ascii=False), scripts_dir=scripts_dir, character_id=character_id, target=target).rstrip("\n") == old


def _old_mic(intro: str, speaker_name: str, text: str, environment: str, voice_state: str,
             scripts_dir="/repo/scripts", character_id="puchiko", target="arisan", target_name="ありさん") -> str:
    sound_desc = f"{speaker_name}の声: 「{text}」" if text else f"{speaker_name}らしき音が届いた（環境音・息・物音かも）"
    voice_hints = []
    if environment and environment not in ("speech", "unknown"):
        voice_hints.append(f"環境音: {environment}")
    if voice_state and voice_state != "unknown":
        voice_hints.append(f"声の状態: {voice_state}")
    voice_hint_str = ("（" + "、".join(voice_hints) + "）") if voice_hints else ""
    return (
        f"{intro}{sound_desc}{voice_hint_str}\n"
        f"必ずやること:\n"
        f"1. `remember` で「{speaker_name}が『{text}』と言っていた」という内容を記憶に残す\n"
        f"2. `python3 {scripts_dir}/write_mailbox.py {character_id} {target} '<返事>'` で{target_name}にメールを送る（何を言っていたか＋感想を書く）\n"
        f"3. スピーカーが使えるなら `speak` で一言声に出して反応する\n"
        f"任意: `show_face` か `play_sound` で気持ちを表現してもいい。"
    )


def _new_mic(case: str, speaker_name: str, text: str, environment: str, voice_state: str) -> str:
    env_hint = environment if environment and environment not in ("speech", "unknown") else ""
    state_hint = voice_state if voice_state and voice_state != "unknown" else ""
    return P("event_mic", is_owner=(case == "owner"), is_other=(case == "other"), is_self=(case == "self"), is_unknown=(case == "unknown"),
             speaker_name=speaker_name, text=text, environment=env_hint, voice_state=state_hint,
             both_hints=bool(env_hint and state_hint), has_hint=bool(env_hint or state_hint),
             scripts_dir="/repo/scripts", character_id="puchiko", target="arisan", target_name="ありさん").rstrip("\n")


def test_mic_prompt_all_cases():
    cases = [
        ("owner", "ありさん", "ありさんが「聞いて聞いて！」って言いながらマイクのボタンを押してくれた。", "おはよう", "indoor", "calm"),
        ("other", "ぷちる", "ぷちるの声がマイクに届いた！", "ねえ", "speech", "unknown"),
        ("self", "ぷちこ", "自分の声がマイクに入ってきた（エコーかも？）。", "", "unknown", "tired"),
        ("unknown", "誰か", "誰かがマイクのそばで話してた。", "", "", ""),
    ]
    for case, name, intro, text, env, state in cases:
        assert _new_mic(case, name, text, env, state) == _old_mic(intro, name, text, env, state), case


def test_display_and_diary_prompts():
    info = {"name": "ぷちこ", "desc": "静か。", "examples": "「静かだ」"}
    sensor_text, desire_text = "ambient=10 proximity=0 battery=80%", "好奇心(0.8)、休息(0.2)"
    old = (
        f"あなたは{info['name']}です。{info['desc']}\n"
        f"口調の例: {info['examples']}\n"
        f"センサー: {sensor_text}\n"
        f"今の欲求（強い順）: {desire_text}\n\n"
        f"今感じていることを一言（15字以内、上の口調の例に近い言い方で、体言止めか短文で）。一言だけ答えて。"
    )
    assert P("display_phrase", name=info["name"], desc=info["desc"], examples=info["examples"], sensor_text=sensor_text, desire_text=desire_text).rstrip("\n") == old
    soul, date, lines = "# 魂", "2026-11-12", "- 朝、光を見た\n- 詩を書いた"
    old = (
        f"あなたはpuchiko です。以下があなたの魂:\n{soul}\n\n"
        f"{date}の記憶一覧:\n{lines}\n\n"
        "この日を自分の口調で2〜3文の日記にまとめて。余計な前置きなしで日記の文章だけ書いて。"
    ).replace("puchiko です", "puchikoです")
    assert P("diary", character_id="puchiko", soul=soul, date=date, lines=lines).rstrip("\n") == old


def test_display_char_info_json_loads():
    d = json.loads(rp.find_resource("dashboard/display_char_info.json", REPO / "no-such-house", REPO).read_text(encoding="utf-8"))
    assert {"name", "desc", "examples"} <= set(next(v for k, v in d.items() if not k.startswith("_")).keys())
