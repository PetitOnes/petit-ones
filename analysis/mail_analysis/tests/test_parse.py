from datetime import date

import parse_mailbox as pm


def test_normalize_date_8digit():
    assert pm.normalize_date("20260305") == "20260305"


def test_normalize_date_7digit_missing_leading_zero():
    # from_yui_to_puchiteya_2026303_1501.md の実例（2026-03-03）
    assert pm.normalize_date("2026303") == "20260303"


def test_normalize_date_invalid_length():
    assert pm.normalize_date("202630") is None


def test_normalize_actor_alias():
    assert pm.normalize_actor("kazehaya") == "kazahaya"
    assert pm.normalize_actor("puchiko") == "puchiko"


def test_week_index_day0_is_week0():
    assert pm.week_index(date(2026, 3, 5)) == 0


def test_week_index_before_day0_is_negative():
    assert pm.week_index(date(2026, 2, 28)) == -1


def test_week_index_next_week():
    assert pm.week_index(date(2026, 3, 12)) == 1


def test_dyad_key_puchi_pair_sorted():
    assert pm.dyad_key("puchiteya", "puchiko") == "puchiko-puchiteya"
    assert pm.dyad_key("puchiko", "puchiteya") == "puchiko-puchiteya"


def test_dyad_key_non_puchi_is_none():
    assert pm.dyad_key("puchiteya", "arisan") is None
    assert pm.dyad_key("puchiteya", "puchiteya") is None


def test_parse_filename_standard():
    result = pm.parse_filename(
        "from_puchiteya_to_puchiko_20260305_1200.md", "テスト本文"
    )
    assert result.skip_reason is None
    assert result.record["sender"] == "puchiteya"
    assert result.record["recipient"] == "puchiko"
    assert result.record["dyad"] == "puchiko-puchiteya"
    assert result.record["week"] == 0
    assert result.record["chars"] == len("テスト本文")


def test_parse_filename_standard_with_seq_suffix():
    result = pm.parse_filename(
        "from_puchiko_to_arisan_20260326_0751_2.md", "本文"
    )
    assert result.skip_reason is None
    assert result.record["dyad"] == ""  # arisan宛は参考系列


def test_parse_filename_malformed_date():
    result = pm.parse_filename(
        "from_yui_to_puchiteya_2026303_1501.md", "はじめまして！"
    )
    assert result.skip_reason is None
    assert result.record["date"] == "2026-03-03"


def test_parse_filename_legacy_with_sender_suffix():
    result = pm.parse_filename(
        "to_arisan_20260301_0305_puchiteya.md", "本文\nぷちてゃ"
    )
    assert result.skip_reason is None
    assert result.record["sender"] == "puchiteya"
    assert result.record["recipient"] == "arisan"


def test_parse_filename_legacy_signature_fallback():
    body = "テストメールだよ。\n\nぷちこ"
    result = pm.parse_filename("to_arisan_20260228_0059.md", body)
    assert result.skip_reason is None
    assert result.record["sender"] == "puchiko"


def test_parse_filename_legacy_signature_undetectable():
    result = pm.parse_filename("to_arisan_20260228_0300.md", "誰の手紙かわからない本文")
    assert result.record is None
    assert "undetectable" in result.skip_reason


def test_parse_filename_reply_tmp_skipped():
    result = pm.parse_filename("reply_to_teya_20260511_tmp.md", "てゃへ。")
    assert result.record is None
    assert "tmp" in result.skip_reason


def test_parse_filename_notebook_recipient_skipped():
    result = pm.parse_filename(
        "from_puchiko_to_notebook_20260413_2250.md", "ノート本文"
    )
    assert result.record is None
    assert "unknown actor" in result.skip_reason


def test_parse_filename_unmatched_pattern():
    result = pm.parse_filename("random_file.md", "本文")
    assert result.record is None
    assert result.skip_reason == "filename does not match known patterns"
