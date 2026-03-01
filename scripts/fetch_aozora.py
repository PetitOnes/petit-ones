"""Fetch and extract text from Aozora Bunko with proper Shift_JIS decoding."""
import urllib.request
import re
import sys

def fetch_aozora(url, page=None, chars_per_page=3000):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()

    # Try Shift_JIS first, then UTF-8
    for enc in ("shift_jis", "utf-8", "euc-jp"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        text = raw.decode("shift_jis", errors="replace")

    # Extract main_text div content
    m = re.search(r'<div class="main_text">(.*?)</div>', text, re.DOTALL)
    if m:
        body = m.group(1)
    else:
        # fallback: extract body
        m = re.search(r'<body[^>]*>(.*?)</body>', text, re.DOTALL)
        body = m.group(1) if m else text

    # Remove ruby annotations but keep base text
    body = re.sub(r'<rp>[^<]*</rp>', '', body)
    body = re.sub(r'<rt>[^<]*</rt>', '', body)
    body = re.sub(r'<ruby>', '', body)
    body = re.sub(r'</ruby>', '', body)

    # Convert <br> to newlines
    body = re.sub(r'<br\s*/?>', '\n', body)

    # Remove remaining HTML tags
    body = re.sub(r'<[^>]+>', '', body)

    # Decode HTML entities
    import html
    body = html.unescape(body)

    # Clean up whitespace
    lines = [line.strip() for line in body.split('\n')]
    body = '\n'.join(lines)
    # Remove excessive blank lines
    body = re.sub(r'\n{3,}', '\n\n', body)
    body = body.strip()

    total_chars = len(body)
    total_pages = (total_chars + chars_per_page - 1) // chars_per_page

    if page is None:
        # Info mode
        print(f"Title: 銀河鉄道の夜")
        print(f"Total characters: {total_chars}")
        print(f"Total pages ({chars_per_page} chars/page): {total_pages}")
        # Show chapter headings
        chapters = re.findall(r'^([\u4e00-\u9fff]+、.+)$', body, re.MULTILINE)
        if chapters:
            print("\nChapters:")
            for ch in chapters:
                print(f"  {ch}")
    else:
        start = (page - 1) * chars_per_page
        end = start + chars_per_page
        chunk = body[start:end]
        # Try to break at a natural point (newline)
        if end < total_chars:
            last_nl = chunk.rfind('\n')
            if last_nl > chars_per_page * 0.7:
                chunk = chunk[:last_nl]
        print(f"--- Page {page}/{total_pages} ---\n")
        print(chunk)
        print(f"\n--- End of page {page}/{total_pages} ---")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.aozora.gr.jp/cards/000081/files/43737_19215.html"
    page = int(sys.argv[2]) if len(sys.argv) > 2 else None
    fetch_aozora(url, page)
