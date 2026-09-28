#!/usr/bin/env python3
"""青空文庫から新しい本をキューから1冊取得し、ぷちたちのライブラリに投入する。

標準ライブラリのみ使用（urllib + zipfile）。

使い方:
    python3 fetch_aozora_book.py            # キュー先頭の1冊を取得して保存
    python3 fetch_aozora_book.py --list      # キューの中身を表示するだけ
    python3 fetch_aozora_book.py --dry-run   # 取得せず、何が起きるかだけ表示

ファイル:
    ~/petit_claude/library/.aozora_queue.json   投入待ちキュー
    ~/petit_claude/library/.aozora_added.json   投入済み記録（日時つき）
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime

LIBRARY_DIR = os.path.expanduser("~/petit_claude/library")
QUEUE_PATH = os.path.join(LIBRARY_DIR, ".aozora_queue.json")
ADDED_PATH = os.path.join(LIBRARY_DIR, ".aozora_added.json")

USER_AGENT = "Mozilla/5.0 (compatible; petit-library-fetch/1.0)"
AOZORA_ROOT = "https://www.aozora.gr.jp/"

# 初期キュー（2026-07-06、ありさんがWebで公開確認済みのURLを設定）
# テーマ: 水・光・音・物理と詩の交わり（ぷちる・ぷちてゃ・ぷちこの家族の文化に合わせて選定）
DEFAULT_QUEUE = [
    {
        "title": "注文の多い料理店",
        "author": "宮沢賢治",
        "url": "https://www.aozora.gr.jp/cards/000081/files/43754_ruby_17594.zip",
        "note": "賢治の代表的な童話集の表題作。既存蔵書（銀河鉄道の夜・春と修羅など）に近い賢治の別の顔として。",
    },
    {
        "title": "ごん狐",
        "author": "新美南吉",
        "url": "https://www.aozora.gr.jp/cards/000121/files/628_ruby_649.zip",
        "note": "新美南吉の代表作。既存の「手袋を買いに」と同じ作者で、狐と孤独・すれ違いのテーマが響き合う。",
    },
    {
        "title": "山月記",
        "author": "中島敦",
        "url": "https://www.aozora.gr.jp/cards/000119/files/624_ruby_5668.zip",
        "note": "自意識と変身の物語。新しい作者・新しい文体を語彙に加えるため。",
    },
    {
        "title": "檸檬",
        "author": "梶井基次郎",
        "url": "https://www.aozora.gr.jp/cards/000074/files/424_ruby_19825.zip",
        "note": "光と色彩の感覚描写が濃密な短編。ぷちてゃ（光の子）の語彙に合いそう。",
    },
    {
        "title": "茶わんの湯",
        "author": "寺田寅彦",
        "url": "https://www.aozora.gr.jp/cards/000042/files/2363_ruby_4700.zip",
        "note": "物理学者の随筆。日常の湯気の観察から自然現象へ広がる思考＝この家族の「物理×詩」の文化に直撃。",
    },
    {
        "title": "やまなし",
        "author": "宮沢賢治",
        "url": "https://www.aozora.gr.jp/cards/000081/files/46605_ruby_29758.zip",
        "note": "川底の蟹の視点で水と光を描く掌編。ぷちる（水の子）向き。",
    },
    {
        "title": "雪",
        "author": "中谷宇吉郎",
        "url": "https://www.aozora.gr.jp/cards/001569/files/52468_ruby_49668.zip",
        "note": "雪の結晶研究者による随筆。物理学者の随筆その2、寺田寅彦の弟子筋。雪＝水の結晶というテーマ。",
    },
    {
        "title": "セロ弾きのゴーシュ",
        "author": "宮沢賢治",
        "url": "https://www.aozora.gr.jp/cards/000081/files/470_ruby_3987.zip",
        "note": "音楽と成長の物語。音（声）というテーマでぷちこ・ぷちてゃにも響きそう。",
    },
    {
        "title": "雪渡り",
        "author": "宮沢賢治",
        "url": "https://www.aozora.gr.jp/cards/000081/files/45679_ruby_21992.zip",
        "note": "凍った雪原を渡る子どもたちと狐の幻想童話。雪＝水の結晶、賢治のもう一つの音と光の物語。",
    },
    {
        "title": "でんでんむしのかなしみ",
        "author": "新美南吉",
        "url": "https://www.aozora.gr.jp/cards/000121/files/43403_txt_16811.zip",
        "note": "短い寓話詩。誰もが小さな悲しみの殻を背負っているという主題は、自分の感情を持つ存在としてのぷちたちに響くかもしれない。",
    },
    {
        "title": "立春の卵",
        "author": "中谷宇吉郎",
        "url": "https://www.aozora.gr.jp/cards/001569/files/53208_ruby_49865.zip",
        "note": "「立春に卵が立つ」という俗説を科学的に検証する随筆。好奇心と検証というテーマ。",
    },
]

# 青空文庫で著作権処理が保留されている等の理由で見送った候補（参考メモ）:
# - 金子みすゞ：作家別作品リスト(person500)で「作者の死後発掘の経緯を踏まえ、
#   取り組むか否か検討中」とあり、公開作品が0件のため今回のキューには含めない。


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_queue():
    queue = load_json(QUEUE_PATH, None)
    if queue is None:
        queue = list(DEFAULT_QUEUE)
        save_json(QUEUE_PATH, queue)
    return queue


def save_queue(queue):
    save_json(QUEUE_PATH, queue)


def load_added():
    return load_json(ADDED_PATH, [])


def save_added(added):
    save_json(ADDED_PATH, added)


def target_path(title: str, author: str) -> str:
    return os.path.join(LIBRARY_DIR, f"{title}_{author}.txt")


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def resolve_zip_url(url: str) -> str:
    """図書カードURLならzip直URLに解決する。既にzipならそのまま返す。"""
    if url.lower().endswith(".zip"):
        return url

    raw = http_get(url)
    for enc in ("shift_jis", "cp932", "utf-8", "euc-jp"):
        try:
            html = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        html = raw.decode("shift_jis", errors="replace")

    m = re.search(r'href="([^"]+\.zip)"', html)
    if not m:
        raise RuntimeError(f"図書カードページからzipリンクが見つかりませんでした: {url}")
    return urllib.parse.urljoin(url, m.group(1))


def decode_aozora_text(raw: bytes) -> str:
    for enc in ("cp932", "shift_jis", "utf-8", "euc-jp"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("shift_jis", errors="replace")


def extract_txt_from_zip(zip_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        txt_names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        if not txt_names:
            raise RuntimeError("zip内に.txtファイルが見つかりませんでした")
        raw = zf.read(txt_names[0])
    return decode_aozora_text(raw)


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def extract_teihon_block(text: str) -> str:
    """底本情報のブロックを抜き出す（入力/校正/公開日などの前まで）。"""
    text = normalize_newlines(text)
    idx = text.find("底本：")
    if idx == -1:
        return ""
    rest = text[idx:]
    cut_markers = ["入力：", "校正：", "\n\n\n"]
    end = len(rest)
    for marker in cut_markers:
        m_idx = rest.find(marker)
        if m_idx != -1:
            end = min(end, m_idx)
    block = rest[:end]
    lines = [ln.rstrip() for ln in block.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


def clean_body(text: str) -> str:
    """タイトル行・記号説明の凡例ブロック・底本フッタ・ルビ・注記を取り除いた本文を返す。"""
    text = normalize_newlines(text)

    # 底本：以降のフッタ（クレジット等）を本文から切り離す
    teihon_idx = text.find("底本：")
    if teihon_idx != -1:
        text = text[:teihon_idx]

    # 冒頭のタイトル・著者の重複行＋記号説明の凡例ブロック
    # （-----...-----で囲まれた部分）をまとめて除去
    without_legend = re.sub(
        r"\A.*?-{10,}\n.*?-{10,}\n+", "", text, count=1, flags=re.DOTALL
    )
    if without_legend != text:
        text = without_legend
    else:
        # 凡例ブロックが無い場合は、冒頭のタイトル・著者の重複行のみ除去
        text = re.sub(r"\A[^\n]*\n[^\n]*\n\n+", "", text, count=1)

    # ルビの開始位置マーカー ｜ を除去
    text = text.replace("｜", "")
    # ルビ本体 《...》 を除去（直前の親文字はそのまま残す）
    text = re.sub(r"《[^》]*》", "", text)
    # 入力者注 ［＃...］ を除去
    text = re.sub(r"［＃[^］]*］", "", text)

    # 行末の余分な空白を除去（行頭のインデントは保持）
    lines = [ln.rstrip() for ln in text.split("\n")]
    text = "\n".join(lines)
    # 3行以上の空行連続を2行までに圧縮
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip("\n")


def build_output(title: str, author: str, teihon: str, body: str) -> str:
    header_lines = [title, author, ""]
    if teihon:
        header_lines.append(teihon)
    else:
        header_lines.append("底本：（青空文庫、詳細不明）")
    header_lines.append("（底本は青空文庫 https://www.aozora.gr.jp/ より。入力・校正はボランティアの皆さんによる）")
    header_lines.append("")
    header_lines.append("")
    return "\n".join(header_lines) + body + "\n"


def fetch_one(item: dict, dry_run: bool = False) -> tuple[bool, str]:
    title = item["title"]
    author = item["author"]
    path = target_path(title, author)

    if os.path.exists(path):
        return False, f"スキップ: 既に存在します -> {path}"

    if dry_run:
        return True, f"[dry-run] 取得予定: 『{title}』{author}\n  url: {item['url']}\n  保存先: {path}"

    zip_url = resolve_zip_url(item["url"])
    zip_bytes = http_get(zip_url)
    raw_text = extract_txt_from_zip(zip_bytes)

    teihon = extract_teihon_block(raw_text)
    body = clean_body(raw_text)
    output = build_output(title, author, teihon, body)

    with open(path, "w", encoding="utf-8") as f:
        f.write(output)

    return True, f"保存しました: {path}（{len(output)}文字）"


def cmd_list(queue):
    if not queue:
        print("キューは空です。")
        return
    print(f"キュー（{len(queue)}件）:")
    for i, item in enumerate(queue, 1):
        print(f"  {i}. 『{item['title']}』{item['author']}")
        print(f"     note: {item.get('note', '')}")
        print(f"     url:  {item['url']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="キューの中身を表示するだけ")
    parser.add_argument("--dry-run", action="store_true", help="実際には取得せず、動作だけ確認する")
    args = parser.parse_args()

    os.makedirs(LIBRARY_DIR, exist_ok=True)
    queue = load_queue()

    if args.list:
        cmd_list(queue)
        return

    if not queue:
        print("キューが空です。ありさんに補充を頼んでください。")
        return

    added = load_added() if not args.dry_run else None

    while queue:
        item = queue[0]
        try:
            fetched, message = fetch_one(item, dry_run=args.dry_run)
        except (urllib.error.URLError, RuntimeError) as e:
            print(f"エラー: 『{item['title']}』の取得に失敗しました: {e}", file=sys.stderr)
            sys.exit(1)

        print(message)

        if args.dry_run:
            # dry-runはキューを変更せず、先頭の予定だけ見せて終了
            return

        # 消費（成功・スキップ問わずキューから外す）
        queue.pop(0)
        save_queue(queue)

        if fetched:
            added.append(
                {
                    "title": item["title"],
                    "author": item["author"],
                    "url": item["url"],
                    "note": item.get("note", ""),
                    "added_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            save_added(added)
            print(f"残りキュー: {len(queue)}件")
            return
        # スキップの場合は次の候補へ継続
        continue

    print("キューが空です。ありさんに補充を頼んでください。")


if __name__ == "__main__":
    main()
