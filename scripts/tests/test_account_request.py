"""ログイン画面からのお願い(scripts/account_request.py)のテスト"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import account_request as ar

T0 = datetime(2026, 11, 14, 16, 0)


def test_clean_keeps_only_what_is_needed():
    req = ar.clean("signup", " new_user ", "あたらしい人\n", "ともだちの\n  ゆいです " + "x" * 400)
    assert req["username"] == "new_user" and req["name"] == "あたらしい人"
    assert "\n" not in req["note"] and len(req["note"]) == 300


@pytest.mark.parametrize("args", [
    ("other", "user", "n", "note"),          # 知らない種類
    ("signup", "bad name", "n", "note"),     # ユーザー名に空白
    ("signup", "../x", "n", "note"),
    ("signup", "", "n", "note"),
    ("signup", "user", "", "note"),          # 新規登録は呼び名が要る
    ("reset", "user", "", ""),               # ひとことが要る
])
def test_clean_refuses(args):
    with pytest.raises(ar.RequestError):
        ar.clean(*args)


def test_reset_does_not_need_a_name():
    assert ar.clean("reset", "user", "", "わすれました")["name"] == ""
    assert ar.clean("reset", "user", "前の欄に残っていた名前", "わすれました")["name"] == ""


def test_limiter_per_ip_and_per_day():
    lim = ar.Limiter(per_ip=2, per_day=5)
    assert lim.allow("a", T0) and lim.allow("a", T0)
    assert not lim.allow("a", T0 + timedelta(minutes=30))      # 同じ場所から 1 時間に 2 通まで
    assert lim.allow("a", T0 + timedelta(hours=1, minutes=1))  # 1 時間たてば、また送れる
    assert lim.allow("b", T0) and lim.allow("c", T0)
    assert not lim.allow("d", T0 + timedelta(hours=2))         # 家ぜんたいで 1 日に 5 通まで
    assert lim.allow("d", T0 + timedelta(days=1, hours=2))


def test_letter_never_holds_a_password_and_tells_the_owner_what_to_do():
    req = ar.clean("signup", "new_user", "あたらしい人", "ゆいです")
    text = ar.letter(req, "192.0.2.5", exists=False)
    assert "新規登録のお願い" in text and "new_user" in text and "192.0.2.5" in text
    assert "auth.json の users に足して" in text
    assert "もう使われています" in ar.letter(req, "", exists=True)
    reset = ar.clean("reset", "someone", "", "わすれました")
    assert "家にいません" in ar.letter(reset, "", exists=False)
    assert "password を変えて" in ar.letter(reset, "", exists=True)


def test_write_does_not_overwrite(tmp_path):
    a = ar.write(tmp_path, "keeper", "one", T0)
    b = ar.write(tmp_path, "keeper", "two", T0)
    assert a.name == "from_login_to_keeper_20261114_1600.md" and b.name == "from_login_to_keeper_20261114_1600_2.md"
    assert a.read_text(encoding="utf-8") == "one"
