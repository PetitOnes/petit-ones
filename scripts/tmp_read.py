"""Temporary script to fetch Haru to Shura from Aozora Bunko."""
import urllib.request
import re
import html as htmlmod
import sys

url = sys.argv[1] if len(sys.argv) > 1 else "https://www.aozora.gr.jp/cards/000081/files/1058_15403.html"
page = int(sys.argv[2]) if len(sys.argv) > 2 else None
chars_per_page = 3000

req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
raw = urllib.request.urlopen(req).read()

for enc in ("shift_jis", "utf-8", "euc-jp"):
    try:
        text = raw.decode(enc)
        break
    except (UnicodeDecodeError, LookupError):
        continue

m = re.search(r'<div class="main_text">(.*?)</div>', text, re.DOTALL)
body = m.group(1) if m else text

body = re.sub(r'<rp>[^<]*</rp>', '', body)
body = re.sub(r'<rt>[^<]*</rt>', '', body)
body = re.sub(r'</?ruby>', '', body)
body = re.sub(r'<br\s*/?>', '\n', body)
body = re.sub(r'<[^>]+>', '', body)
body = htmlmod.unescape(body)

lines = [l.strip() for l in body.split('\n')]
body = '\n'.join(lines)
body = re.sub(r'\n{3,}', '\n\n', body)
body = body.strip()

total_chars = len(body)
total_pages = (total_chars + chars_per_page - 1) // chars_per_page

if page is None:
    print(f"Total characters: {total_chars}")
    print(f"Total pages ({chars_per_page} chars/page): {total_pages}")
else:
    start = (page - 1) * chars_per_page
    end = start + chars_per_page
    chunk = body[start:end]
    if end < total_chars:
        last_nl = chunk.rfind('\n')
        if last_nl > chars_per_page * 0.7:
            chunk = chunk[:last_nl]
    print(f"--- Page {page}/{total_pages} ---\n")
    print(chunk)
    print(f"\n--- End of page {page}/{total_pages} ---")
