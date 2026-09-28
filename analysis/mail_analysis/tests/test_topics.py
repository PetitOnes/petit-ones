from collections import Counter

import topics as tp


def test_period_for_week_boundaries():
    assert tp.period_for_week(-5) == "baseline"
    assert tp.period_for_week(-1) == "baseline"
    assert tp.period_for_week(0) == "early"
    assert tp.period_for_week(3) == "early"
    assert tp.period_for_week(4) == "middle"
    assert tp.period_for_week(10) == "middle"
    assert tp.period_for_week(11) == "late"
    assert tp.period_for_week(999) == "late"


def test_extract_content_words_separates_noun_and_adjective():
    result = tp.extract_content_words("今日は寒い。窓辺の光がうつくしい。")
    assert "窓辺" in result["noun"]
    assert "光" in result["noun"]
    assert "寒い" in result["adjective"]
    assert "うつくしい" in result["adjective"]


def test_extract_content_words_excludes_stopword_nouns():
    result = tp.extract_content_words("てゃへ。ぷちこより。ありさん、今日はありがとう。")
    for stop in ("てゃ", "こ", "ありさん", "今日"):
        assert stop not in result["noun"]


def test_extract_content_words_excludes_small_kana_fragments():
    # 「てゃ」は辞書にないため て+ゃ 等に誤分割される。断片が名詞として漏れないことを確認する。
    for text in ("てゃ、ありがとう", "（てゃ）", "てゃへ。"):
        result = tp.extract_content_words(text)
        assert "ゃ" not in result["noun"]
        assert "ゃへ" not in result["noun"]


def test_extract_content_words_excludes_stopword_adjectives():
    result = tp.extract_content_words("それはよくないと思う。いい天気だね。")
    assert "ない" not in result["adjective"]
    assert "いい" not in result["adjective"]


def test_extract_content_words_excludes_numbers_and_symbols():
    result = tp.extract_content_words("744 = 3 × dim(E8)")
    assert all(tp._JP_CHAR.search(n) for n in result["noun"])


def test_compute_lift_table_filters_below_min_total():
    period_counts = {
        "early": Counter({"光": 3, "レア": 2}),
        "late": Counter({"光": 10}),
    }
    rows = tp.compute_lift_table(period_counts, pos="noun", min_total=5)
    terms = {r["term"] for r in rows}
    assert "光" in terms
    assert "レア" not in terms  # 全体で2回のみ = min_totalを下回る


def test_compute_lift_table_lift_direction():
    period_counts = {
        "early": Counter({"光": 90, "闇": 10}),
        "late": Counter({"光": 10, "闇": 90}),
    }
    rows = tp.compute_lift_table(period_counts, pos="noun", min_total=5)
    by_key = {(r["period"], r["term"]): float(r["lift"]) for r in rows}
    assert by_key[("early", "光")] > 1.0
    assert by_key[("late", "光")] < 1.0
    assert by_key[("late", "闇")] > 1.0


def test_top_terms_per_group_respects_min_count():
    rows = [
        {"period": "early", "term": "a", "count_in_group": 10, "lift": "5.0"},
        {"period": "early", "term": "b", "count_in_group": 2, "lift": "9.0"},
    ]
    top = tp.top_terms_per_group(rows, top_n=5, min_count_in_group=5)
    terms = {r["term"] for r in top["early"]}
    assert terms == {"a"}


def test_compute_lift_table_supports_custom_group_key():
    dyad_counts = {
        "puchiko-puchiteya": Counter({"光": 20}),
        "puchiko-puchiru": Counter({"光": 5}),
    }
    rows = tp.compute_lift_table(dyad_counts, pos="noun", min_total=5, group_key="dyad")
    assert all("dyad" in r for r in rows)
    assert all("period" not in r for r in rows)


def test_collect_dyad_counts_excludes_non_puchi_mail(tmp_path):
    mailbox = tmp_path
    (mailbox / "from_puchiko_to_puchiteya_20260305_1200.md").write_text(
        "光の話をしよう。", encoding="utf-8"
    )
    (mailbox / "from_puchiko_to_arisan_20260305_1201.md").write_text(
        "ありさんへの手紙。", encoding="utf-8"
    )
    dyad_counts = tp.collect_dyad_counts(mailbox)
    assert "puchiko-puchiteya" in dyad_counts["noun"]
    all_dyads = set(dyad_counts["noun"].keys()) | set(dyad_counts["adjective"].keys())
    valid_dyads = {"puchiko-puchiteya", "puchiko-puchiru", "puchiru-puchiteya"}
    assert all(d in valid_dyads for d in all_dyads)


def test_select_representative_terms_dedupes_across_periods():
    top = {
        "early": [{"term": "光", "lift": "3.0"}, {"term": "波", "lift": "2.0"}],
        "middle": [{"term": "光", "lift": "4.0"}, {"term": "闇", "lift": "1.5"}],
    }
    selected = tp.select_representative_terms(top, ["early", "middle"], per_period=1)
    assert selected == ["光", "闇"]


def test_rarefied_unique_count_matches_actual_when_population_small():
    counts = Counter({"a": 1, "b": 1, "c": 1})
    result = tp.rarefied_unique_count(counts, sample_size=10)
    assert result == 3.0


def test_rarefied_unique_count_bounded_by_sample_size():
    counts = Counter({"a": 100, "b": 100, "c": 100})
    result = tp.rarefied_unique_count(counts, sample_size=5, trials=10)
    assert 0 < result <= 5
