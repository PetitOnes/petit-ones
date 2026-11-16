"""スマホの居場所(scripts/phone_place.py)のテスト"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import phone_place as pp  # noqa: E402
import whereabouts as wa  # noqa: E402

T = datetime(2026, 11, 14, 21, 0)


def _house(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "spots.json").write_text(json.dumps({"spots": [
        {"id": "a1", "room": "あり部屋", "spot": "ソファ", "devices": ["DFE455C969D7", "84F703B4BB6A"]},
        {"id": "a2", "room": "あり部屋", "spot": "机", "devices": ["DFE455C969D7"]},
        {"id": "b1", "room": "寝室", "spot": "窓際", "devices": ["70041D7E07AE"]},
    ]}), encoding="utf-8")
    pp.make_key("arisan", "ありさんのスマホ", tmp_path)
    return tmp_path


def test_key_and_macs(tmp_path):
    base = _house(tmp_path)
    key = json.loads(pp.config_path(base).read_text(encoding="utf-8"))["phones"]["arisan"]["key"]
    assert len(key) > 30 and pp.person_for_key(key, base) == "arisan"
    assert pp.person_for_key("x", base) is None and pp.person_for_key(None, base) is None
    assert pp.macs(base) == ["70041D7E07AE", "84F703B4BB6A", "DFE455C969D7"]
    assert pp.rooms_from_seen({"df:e4:55:c9:69:d7": -60, "84F703B4BB6A": -55, "70041D7E07AE": -99, "FFFFFFFFFFFF": -10}, base) == {"あり部屋": -55}


def test_report_hysteresis_and_lines(tmp_path):
    base = _house(tmp_path)
    r = pp.report("arisan", {"DFE455C969D7": -60}, base, T)
    assert r["room"] == "あり部屋" and r["since"] == T.isoformat()
    # 寝室が 3 dB だけ強くても、まだ動かない(6 dB の決まり)
    r = pp.report("arisan", {"DFE455C969D7": -60, "70041D7E07AE": -57}, base, T + timedelta(seconds=30))
    r = pp.report("arisan", {"DFE455C969D7": -60, "70041D7E07AE": -57}, base, T + timedelta(seconds=60))
    assert r["room"] == "あり部屋"
    # 寝室がはっきり強い報告が続けば(まんなかが寝室)、移る
    for i in range(3, 6):
        r = pp.report("arisan", {"DFE455C969D7": -80, "70041D7E07AE": -50}, base, T + timedelta(seconds=30 * i))
    assert r["room"] == "寝室" and r["since"] == (T + timedelta(seconds=30 * 4)).isoformat()
    label = lambda u: {"arisan": "ありさん"}.get(u, u)  # noqa: E731
    assert pp.lines(base, label, T + timedelta(seconds=160)) == ["ありさんのスマホ: 家(寝室)"]
    assert wa.lines(base, label=label, now=T + timedelta(seconds=160)) == []   # 毎回は渡さない(見に行けるもの)
    # 古くなれば、何も言わない
    assert pp.where("arisan", base, T + timedelta(seconds=150 + 300)) is None
    assert pp.lines(base, label, T + timedelta(seconds=150 + 300)) == []


def test_no_beacon_seen(tmp_path):
    base = _house(tmp_path)
    for i in range(3):
        r = pp.report("arisan", {}, base, T + timedelta(seconds=30 * i))
    assert r["room"] is None
    assert pp.lines(base, lambda u: "ありさん", T + timedelta(seconds=70)) == ["ありさんのスマホ: 家の印が見えない(お外か、印の無い部屋)"]


def test_no_config(tmp_path):
    assert pp.config(tmp_path)["phones"] == {}
    assert pp.lines(tmp_path) == []
    assert wa.lines(tmp_path, now=T) == []


def test_first_sighting_after_empty_reports_does_not_pick_a_room_by_tie(tmp_path):
    """空の報告 2 回のあとに初めて印が見えても、まんなかが -100 同士の引き分けで部屋を決めない(2026-11-14 実機)"""
    base = _house(tmp_path)
    pp.report("arisan", {}, base, T)
    pp.report("arisan", {}, base, T + timedelta(seconds=30))
    r = pp.report("arisan", {"DFE455C969D7": -44, "70041D7E07AE": -52}, base, T + timedelta(seconds=60))
    assert r["room"] is None
    r = pp.report("arisan", {"DFE455C969D7": -44, "70041D7E07AE": -52}, base, T + timedelta(seconds=90))
    assert r["room"] == "あり部屋"
    assert pp.decide(None, {"寝室": -100, "あり部屋": -100}, 6) is None


def test_change_line_only_when_moved(tmp_path):
    base = _house(tmp_path)
    for i in range(3):
        pp.report("arisan", {"DFE455C969D7": -50}, base, T + timedelta(seconds=30 * i))
    t = T + timedelta(seconds=70)
    assert pp.change_line(base, "puchiko", mark=True, now=t) == ""          # はじめては覚えるだけ
    assert pp.change_line(base, "puchiko", mark=True, now=t) == ""          # 変わっていない
    for i in range(3, 6):
        pp.report("arisan", {"70041D7E07AE": -45}, base, T + timedelta(seconds=30 * i))
    t = T + timedelta(seconds=160)
    assert pp.change_line(base, "puchiko", mark=False, now=t) == "ありさんのスマホ: あり部屋 → 寝室 に動いた"
    assert pp.change_line(base, "puchiko", mark=True, now=t) == "ありさんのスマホ: あり部屋 → 寝室 に動いた"   # mark 無しでは覚えない
    assert pp.change_line(base, "puchiko", mark=True, now=t) == ""
    assert pp.change_line(base, "puchiteya", mark=True, now=t) == ""        # 子ごとに別
    for i in range(6, 9):
        pp.report("arisan", {}, base, T + timedelta(seconds=30 * i))
    t = T + timedelta(seconds=250)
    assert pp.change_line(base, "puchiko", mark=True, now=t) == "ありさんのスマホ: 家の印が見えなくなった(お外に出たか、印の無い部屋)"
    for i in range(9, 12):
        pp.report("arisan", {"DFE455C969D7": -50}, base, T + timedelta(seconds=30 * i))
    t = T + timedelta(seconds=340)
    assert pp.change_line(base, "puchiko", mark=True, now=t) == "ありさんのスマホ: 家(あり部屋)に戻ってきた"
    # 報告が古くなったら、分からないので何も言わず、覚えも変えない
    assert pp.change_line(base, "puchiko", mark=True, now=t + timedelta(seconds=600)) == ""


NETS = pp.local_nets([
    {"ifname": "lo", "addr_info": [{"local": "127.0.0.1", "prefixlen": 8, "scope": "host"}]},
    {"ifname": "wlan0", "addr_info": [{"local": "192.168.1.10", "prefixlen": 24, "scope": "global"},
                                      {"local": "2001:db8:1:2::10", "prefixlen": 64, "scope": "global"},
                                      {"local": "fe80::1", "prefixlen": 64, "scope": "link"}]},
    {"ifname": "tailscale0", "addr_info": [{"local": "100.64.0.1", "prefixlen": 32, "scope": "global"}]},
    {"ifname": "docker0", "addr_info": [{"local": "172.17.0.1", "prefixlen": 16, "scope": "global"}]},
])


def _status(cur: str) -> dict:
    return {"Peer": {"k1": {"TailscaleIPs": ["100.64.0.9", "fd7a:115c:a1e0::9"], "CurAddr": cur},
                     "k2": {"TailscaleIPs": ["100.64.0.8"], "CurAddr": "192.168.1.77:41641"}}}


def test_on_home_net():
    assert [str(n) for n in NETS] == ["192.168.1.0/24", "2001:db8:1:2::/64"]   # lo・tailscale・docker は家のネットワークに数えない
    assert pp.on_home_net("192.168.1.23", {}, NETS) is True                     # 家の中から直に届いた
    assert pp.on_home_net("100.64.0.9", _status("192.168.1.23:41641"), NETS) is True
    assert pp.on_home_net("100.64.0.9", _status("[2001:db8:1:2:aa::5]:40321"), NETS) is True
    assert pp.on_home_net("100.64.0.9", _status("[2001:db8:9:9::5]:40321"), NETS) is False   # テザリング・出先
    assert pp.on_home_net("100.64.0.9", _status("203.0.113.5:1234"), NETS) is False
    assert pp.on_home_net("100.64.0.9", _status(""), NETS) is None              # 中継ごし。分からない
    assert pp.on_home_net("100.64.0.7", _status(""), NETS) is None              # 知らない相手
    assert pp.on_home_net("127.0.0.1", _status(""), NETS) is None               # プロキシごし
    assert pp.on_home_net("100.64.0.9", _status("192.168.1.23:41641"), []) is None
    assert pp.on_home_net(None, {}, NETS) is None


def test_out_or_room_without_beacon(tmp_path):
    base = _house(tmp_path)
    label = lambda u: {"arisan": "ありさん"}.get(u, u)  # noqa: E731
    # 印が見えていれば、家の Wi-Fi でなくても家
    pp.report("arisan", {"DFE455C969D7": -60}, base, T, home=False)
    assert pp.lines(base, label, T) == ["ありさんのスマホ: 家(あり部屋)"]
    assert pp.change_line(base, "puchiko", mark=True, now=T) == ""   # はじめての回は覚えるだけ
    # 印が見えなくなって、家の Wi-Fi にもいない → お外
    for i in range(1, 4):
        pp.report("arisan", {}, base, T + timedelta(seconds=30 * i), home=False)
    t = T + timedelta(seconds=90)
    assert pp.where("arisan", base, t)["home"] is False
    assert pp.lines(base, label, t) == ["ありさんのスマホ: お外(家の印も、家の Wi-Fi も見えない)"]
    assert pp.change_line(base, "puchiko", mark=True, now=t) == "ありさんのスマホ: お外に出た(家の印も、家の Wi-Fi も見えなくなった)"
    # 中継ごしで分からない回は、前のを持ち越す。古くなれば「分からない」に戻るが、ぷちには言い直さない
    pp.report("arisan", {}, base, t + timedelta(seconds=30), home=None)
    assert pp.where("arisan", base, t + timedelta(seconds=30))["home"] is False
    t2 = t + timedelta(seconds=600)
    pp.report("arisan", {}, base, t2, home=None)
    assert pp.where("arisan", base, t2)["home"] is None
    assert pp.lines(base, label, t2) == ["ありさんのスマホ: 家の印が見えない(お外か、印の無い部屋)"]
    assert pp.change_line(base, "puchiko", mark=True, now=t2) == ""
    # 家の Wi-Fi に戻った(印はまだ見えない部屋)
    pp.report("arisan", {}, base, t2 + timedelta(seconds=30), home=True)
    t3 = t2 + timedelta(seconds=30)
    assert pp.lines(base, label, t3) == ["ありさんのスマホ: 家(印の無い部屋。家の Wi-Fi にいる)"]
    assert pp.change_line(base, "puchiko", mark=True, now=t3) == "ありさんのスマホ: 家に戻ってきた(印の無い部屋)"
    # 印のある部屋へ
    for i in range(1, 4):
        pp.report("arisan", {"70041D7E07AE": -50}, base, t3 + timedelta(seconds=30 * i), home=True)
    t4 = t3 + timedelta(seconds=90)
    assert pp.change_line(base, "puchiko", mark=True, now=t4) == "ありさんのスマホ: 寝室 に動いた"
    # 印の無い部屋へ(家の Wi-Fi のまま)
    for i in range(1, 4):
        pp.report("arisan", {}, base, t4 + timedelta(seconds=30 * i), home=True)
    assert pp.change_line(base, "puchiko", mark=True, now=t4 + timedelta(seconds=90)) == "ありさんのスマホ: 寝室 から、印の無い部屋に動いた"
