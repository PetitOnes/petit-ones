"""手紙の Slack 通知(scripts/mail_notify.py)のテスト"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mail_notify as mn  # noqa: E402

DAY = datetime(2026, 11, 14, 21, 0)
NIGHT = datetime(2026, 11, 15, 3, 0)
MORNING = datetime(2026, 11, 15, 7, 5)


def _mail(base, name, read_by=None):
    box = base / "mailbox"
    box.mkdir(exist_ok=True)
    (box / name).write_text("ないしょの本文", encoding="utf-8")
    if read_by:
        p = box / ".metadata.json"
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"mails": {}}
        d["mails"][name] = {"read_by": read_by}
        p.write_text(json.dumps(d), encoding="utf-8")


def test_clean_and_quiet():
    assert mn.clean(None) == {"on": False, "to": "", "house": False, "quiet": None}
    assert mn.clean({"on": True, "to": " C0123ABCD ", "quiet": ["0", 7]}) == {"on": True, "to": "C0123ABCD", "house": False, "quiet": [0, 7]}
    assert mn.clean({"quiet": [3, 3]})["quiet"] is None
    for bad in ({"to": "#general"}, {"to": "xoxb-secret"}, {"quiet": [0, 24]}, {"quiet": "x"}):
        with pytest.raises(ValueError):
            mn.clean(bad)
    assert mn.is_quiet([0, 7], NIGHT) and not mn.is_quiet([0, 7], MORNING) and not mn.is_quiet(None, NIGHT)
    assert mn.is_quiet([22, 7], datetime(2026, 11, 14, 23, 0)) and not mn.is_quiet([22, 7], DAY)


def test_run_tells_new_unread_once_and_holds_at_night(tmp_path):
    sent = []
    send = lambda text, ch: sent.append((text, ch)) or True  # noqa: E731
    _mail(tmp_path, "from_teya_to_ari_20261114_1000.md")   # 入れる前からあった手紙
    mn.save_user(tmp_path, "ari", {"on": True, "to": "C0123ABCD", "quiet": [0, 7]})
    assert mn.run(tmp_path, DAY, send) == [] and sent == []   # はじめての回は、何も送らない
    _mail(tmp_path, "from_teya_to_ari_20261114_2050.md")
    _mail(tmp_path, "from_teya_to_ari_20261114_2051.md")
    _mail(tmp_path, "from_ko_to_ari_20261114_2052.md")
    _mail(tmp_path, "from_ko_to_ari_20261114_2053.md", read_by=["ari"])   # もう読んだ
    _mail(tmp_path, "from_house_to_ari_20261114_2054.md")                 # 家の知らせは数えない
    _mail(tmp_path, "from_teya_to_kaze_20261114_2055.md")                 # ほかの人あて
    assert mn.run(tmp_path, DAY, send) == [("ari", 3)]
    assert sent == [("📬 手紙が 3 通届いています(teya 2、ko 1)", "C0123ABCD")] and "ないしょ" not in sent[0][0]
    assert mn.run(tmp_path, DAY, send) == [] and len(sent) == 1   # 同じ手紙は 2 回知らせない
    # 夜のあいだは送らず、明けてからまとめて 1 回
    _mail(tmp_path, "from_ru_to_ari_20261115_0200.md")
    _mail(tmp_path, "from_ru_to_ari_20261115_0230.md")
    assert mn.run(tmp_path, NIGHT, send) == [] and len(sent) == 1
    assert mn.run(tmp_path, MORNING, send) == [("ari", 2)] and sent[-1][0] == "📬 手紙が 2 通届いています(ru 2)"


def test_run_off_no_channel_and_failed_send(tmp_path):
    sent = []
    ok = lambda text, ch: sent.append(ch) or True  # noqa: E731
    mn.save_user(tmp_path, "ari", {"on": True, "to": "C0123ABCD"})
    mn.save_user(tmp_path, "kaze", {"on": True, "to": ""})   # 送り先なし(家のチャンネルも使わない)
    mn.run(tmp_path, DAY, ok)
    _mail(tmp_path, "from_teya_to_ari_20261114_2050.md")
    _mail(tmp_path, "from_teya_to_kaze_20261114_2050.md")
    assert mn.run(tmp_path, DAY, lambda t, c: False) == []   # 送れなかったら、次の回にまた試す
    assert mn.run(tmp_path, DAY, ok) == [("ari", 1)] and sent == ["C0123ABCD"]
    # 止めているあいだに届いた分は、また出すようにしても、まとめて知らせない
    mn.save_user(tmp_path, "ari", {"on": False, "to": "C0123ABCD"})
    _mail(tmp_path, "from_ko_to_ari_20261114_2100.md")
    assert mn.run(tmp_path, DAY, ok) == []
    mn.save_user(tmp_path, "ari", {"on": True, "to": "C0123ABCD"})
    assert mn.run(tmp_path, DAY, ok) == [] and sent == ["C0123ABCD"]
    with pytest.raises(ValueError):
        mn.try_send(tmp_path, "kaze", ok)
    assert mn.try_send(tmp_path, "ari", ok) is True
