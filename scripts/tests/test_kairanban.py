"""回覧板の一覧と既読(scripts/kairanban.py)のテスト"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import kairanban as kb  # noqa: E402

BODY = "# 回覧板 号外\n\n" + "\n".join(f"- {i} ばんめの知らせ。読むだけでいい。場所の見立ての話" for i in range(12)) + "\n"


def test_parse_name():
    assert kb.parse_name("2026-11-14_2100_basho_kamo.md") == {"date": "2026-11-14", "time": "21:00", "topic": "basho_kamo"}
    assert kb.parse_name("2026-09-07.md") == {"date": "2026-09-07", "time": "", "topic": ""}
    assert kb.parse_name("2026-10-07_claude_code_meetup.md") == {"date": "2026-10-07", "time": "", "topic": "claude_code_meetup"}
    assert kb.parse_name("2026-11-14_2100.md") == {"date": "2026-11-14", "time": "21:00", "topic": ""}
    assert kb.parse_name("2026-11-14_2026_matome.md")["time"] == "20:26"
    assert kb.parse_name("2026-11-14_9999_x.md") == {"date": "2026-11-14", "time": "", "topic": "9999_x"}   # 時刻でない 4 桁は話題
    assert kb.parse_name("README.md") is None and kb.parse_name("memo.md") is None and kb.parse_name("2026-13-40.md") is None


def test_list_issues_delivery_and_read(tmp_path):
    k = tmp_path / "kairanban"
    k.mkdir()
    (k / "README.md").write_text("# きまり", encoding="utf-8")
    (k / "2026-11-14_2100_basho_kamo.md").write_text(BODY, encoding="utf-8")
    (k / "2026-11-01.md").write_text("みじかい号。見出しなし。" * 10, encoding="utf-8")
    box = tmp_path / "mailbox"
    box.mkdir()
    # 届けた手紙は、頭に 1 行足されていても同じ号と分かる。ぷちどうしの手紙・日付の遠い手紙は数えない
    (box / "from_arisan_to_teya_20261114_2105.md").write_text("差出人: ありさん\n\n" + BODY, encoding="utf-8")
    (box / "from_arisan_to_ko_20261114_2106.md").write_text(BODY, encoding="utf-8")
    (box / "from_teya_to_ru_20261114_2110.md").write_text(BODY, encoding="utf-8")
    (box / "from_arisan_to_ru_20261201_0900.md").write_text(BODY, encoding="utf-8")
    (box / ".metadata.json").write_text(json.dumps({"mails": {"from_arisan_to_teya_20261114_2105.md": {"read_by": ["teya"]}}}), encoding="utf-8")
    new, old = kb.list_issues(tmp_path, ["teya", "ko", "ru"])
    assert new["title"] == "回覧板 号外" and (new["date"], new["time"], new["sent"]) == ("2026-11-14", "21:05", True)
    assert new["readers"] == [{"id": "teya", "state": "read"}, {"id": "ko", "state": "unread"}, {"id": "ru", "state": "none"}]
    assert (old["date"], old["time"], old["sent"]) == ("2026-11-01", "", False) and old["title"] == "2026-11-01"
    assert all(r["state"] == "none" for r in old["readers"])
    assert kb.list_issues(tmp_path / "nowhere", ["teya"]) == []
