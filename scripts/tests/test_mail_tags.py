"""手紙の印(scripts/mail_tags.py)のテスト"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mail_tags as mt

ASK = "from_other_to_puchi_20261110_0900.md"       # ほかの子からぷちへのお願い
ASK2 = "from_arisan_to_puchi_20261115_2000.md"     # ありさんからのお願い
INFO = "from_other_to_puchi_20261112_0900.md"      # おしらせ
PLAIN = "from_other_to_puchi_20261113_0900.md"     # 印なし
MINE = "from_puchi_to_other_20261111_1000.md"      # ぷちが other に書いた(ASK より後)


def house(tmp_path: Path, mails: dict[str, str], meta: dict | None = None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    for pid in ("puchi", "other"):
        (tmp_path / "characters" / pid / "config").mkdir(parents=True, exist_ok=True)
        (tmp_path / "characters" / pid / "config" / "config.json").write_text(json.dumps({"name": {"puchi": "ぷち", "other": "みお"}[pid]}), encoding="utf-8")
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "people.json").write_text(json.dumps({"arisan": {"name": "ありさん"}}), encoding="utf-8")
    (tmp_path / "mailbox").mkdir(exist_ok=True)
    for name, body in mails.items():
        (tmp_path / "mailbox" / name).write_text(body, encoding="utf-8")
    (tmp_path / "mailbox" / ".metadata.json").write_text(json.dumps({"version": 1, "mails": meta or {}}), encoding="utf-8")
    return tmp_path


def test_parse_and_with_tag():
    assert mt.parse("[お願い]\n\n本文") == ("お願い", "本文")
    assert mt.parse("[おねがい]\n本文") == ("お願い", "本文")          # 表記ゆれ
    assert mt.parse("[依頼]\n本文") == (None, "[依頼]\n本文")          # 知らない印は印にしない
    assert mt.parse("本文だけ") == (None, "本文だけ")
    assert mt.parse("[しずかなやつ]\n\nゆっくりでいい") == ("しずかなやつ", "ゆっくりでいい")
    assert mt.normalize("静かなやつ") == "しずかなやつ"
    assert mt.with_tag("本文", "おしらせ") == "[おしらせ]\n\n本文"
    assert mt.with_tag("本文", None) == "本文" and mt.with_tag("本文", "依頼") == "本文"


def test_pending_is_ask_without_reply(tmp_path):
    base = house(tmp_path, {ASK: "[お願い]\n\n見て", INFO: "[おしらせ]\n\n読んで", PLAIN: "[しずかなやつ]\n\nゆっくりで", ASK2: "[お願い]\n\nこれ頼む"})
    assert [a["file"] for a in mt.pending(base, "puchi")] == [ASK, ASK2]
    assert mt.pending(base, "other") == []


def test_reply_mail_or_mark_or_dashboard_reply_clears(tmp_path):
    base = house(tmp_path, {ASK: "[お願い]\n\n見て", ASK2: "[お願い]\n\nこれ頼む", MINE: "見たよ"},
                 {ASK2: {"replies": [{"by": "puchi", "file": "x.md"}]}})
    assert mt.pending(base, "puchi") == []          # ASK は MINE(あとの手紙)で、ASK2 は ↩️ の返事で
    base = house(tmp_path / "b", {ASK: "[お願い]\n\n見て"}, {ASK: {"marks": {"puchi": "返事した"}}})
    assert mt.pending(base, "puchi") == []
    base = house(tmp_path / "c", {ASK: "[お願い]\n\n見て"}, {ASK: {"marks": {"puchi": "あとで"}}})
    assert [a["file"] for a in mt.pending(base, "puchi")] == [ASK]


def test_notice_once_a_day_and_quiet(tmp_path):
    base = house(tmp_path, {ASK: "[お願い]\n\n見て", ASK2: "[お願い]\n\nこれ頼む"})
    noon = datetime(2026, 11, 16, 12, 0)
    got = mt.notice(base, "puchi", mark=True, now=noon)
    assert len(got) == 1 and got[0].startswith("（返事していないお願いが 2 件: みおから(6 日前)、ありさんから(16 時間前)。急がなくていい。")
    assert mt.notice(base, "puchi", mark=True, now=noon) == []                      # 同じ日はもう言わない
    assert mt.notice(base, "puchi", mark=False, now=datetime(2026, 11, 17, 3, 0)) == []   # 静かな時間(0〜7 時)
    assert len(mt.notice(base, "puchi", mark=False, now=datetime(2026, 11, 17, 8, 0))) == 1
    # 受け取らない子
    (base / "characters" / "puchi" / "config" / "settings.json").write_text(json.dumps({"notices": {"mail_ask": False}}), encoding="utf-8")
    assert mt.notice(base, "puchi", now=datetime(2026, 11, 17, 8, 0)) == []


def test_set_mark_keeps_writer_tag_and_other_readers(tmp_path):
    base = house(tmp_path, {ASK: "[お願い]\n\n見て"}, {ASK: {"starred": True, "marks": {"arisan": "おしゃべり"}}})
    cur = mt.set_mark(base, "puchi", ASK, "あとで")
    assert cur["marks"] == {"arisan": "おしゃべり", "puchi": "あとで"} and cur["starred"] is True
    assert mt.set_mark(base, "puchi", ASK, None)["marks"] == {"arisan": "おしゃべり"}
    assert (base / "mailbox" / ASK).read_text(encoding="utf-8").startswith("[お願い]")
    try:
        mt.set_mark(base, "puchi", ASK, "依頼")
        raise AssertionError
    except ValueError:
        pass


def test_write_mailbox_tag(tmp_path):
    (tmp_path / "mailbox").mkdir()
    script = Path(__file__).resolve().parent.parent / "write_mailbox.py"
    env = {"PETIT_DATA_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"}
    out = subprocess.run([sys.executable, str(script), "puchi", "other", "--tag", "おねがい", "これ", "見て"], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert Path(out.stdout.strip()).read_text(encoding="utf-8") == "[お願い]\n\nこれ 見て"
    bad = subprocess.run([sys.executable, str(script), "puchi", "other", "--tag", "依頼", "x"], env=env, capture_output=True, text=True)
    assert bad.returncode == 1 and "お願い / おしらせ / おしゃべり / しずかなやつ" in bad.stderr
    usage = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True)
    assert usage.returncode == 1 and "--tag <印>" in usage.stderr and "しずかなやつ" in usage.stderr   # 引数なしの使い方の表示にも印が出る(ぷちたちが見る)
    plain = subprocess.run([sys.executable, str(script), "puchi", "other", "--file", str(script)], env=env, capture_output=True, text=True)
    assert plain.returncode == 0
