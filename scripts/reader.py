# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "readability-lxml>=0.8",
#     "requests>=2.31",
#     "lxml>=5.0",
#     "cssselect>=1.2",
# ]
# ///
"""Web page reader - extracts main content using readability algorithm."""

import argparse
import re
import sys
from pathlib import Path

import requests
from readability import Document

CHARS_PER_PAGE = 2000


def detect_encoding(response: requests.Response) -> str:
    """Detect encoding from Content-Type header, meta charset, or chardet."""
    # 1. Content-Type header charset
    content_type = response.headers.get("Content-Type", "")
    match = re.search(r"charset=([^\s;]+)", content_type, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # 2. HTML meta charset (scan first 4KB of raw bytes)
    head = response.content[:4096]
    # <meta charset="...">
    match = re.search(rb'<meta[^>]+charset=["\']?([^"\'\s;>]+)', head, re.IGNORECASE)
    if match:
        return match.group(1).decode("ascii", errors="ignore")
    # <meta http-equiv="Content-Type" content="text/html; charset=...">
    match = re.search(
        rb'<meta[^>]+content=["\'][^"\']*charset=([^"\'\s;>]+)', head, re.IGNORECASE
    )
    if match:
        return match.group(1).decode("ascii", errors="ignore")

    # 3. Fallback to apparent_encoding (chardet)
    return response.apparent_encoding or "utf-8"


def fetch_html(url: str) -> str:
    """Fetch URL content with proper encoding detection."""
    resp = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ShiroeReader/1.0)"},
        timeout=30,
    )
    resp.raise_for_status()

    encoding = detect_encoding(resp)
    return resp.content.decode(encoding, errors="replace")


def read_local_file(path_str: str) -> str:
    """Read a local HTML file."""
    p = Path(path_str).resolve()
    if not p.exists():
        print(f"File not found: {p}", file=sys.stderr)
        sys.exit(1)
    # Try utf-8 first, then shift_jis, then fallback
    for enc in ("utf-8", "shift_jis", "euc-jp", "iso-2022-jp"):
        try:
            return p.read_text(encoding=enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return p.read_text(encoding="utf-8", errors="replace")


def extract_content(html: str, url: str = "") -> tuple[str, str]:
    """Extract title and text content using readability."""
    doc = Document(html, url=url)
    title = doc.short_title() or "(no title)"
    # Get text content from the summary HTML
    summary_html = doc.summary()
    # Strip HTML tags to get plain text
    from lxml.html import fromstring, tostring

    tree = fromstring(summary_html)
    text = tree.text_content().strip()
    return title, text


def main() -> None:
    parser = argparse.ArgumentParser(description="Web page reader (readability mode)")
    parser.add_argument("url", help="URL or local file path")
    parser.add_argument("--page", type=int, default=None, help="Show only page N (1-indexed)")
    parser.add_argument("--info", action="store_true", help="Show title and page count only")
    args = parser.parse_args()

    url = args.url
    is_local = not url.startswith(("http://", "https://"))

    if is_local:
        html = read_local_file(url)
    else:
        try:
            html = fetch_html(url)
        except requests.RequestException as e:
            print(f"Fetch failed: {e}", file=sys.stderr)
            sys.exit(1)

    title, text = extract_content(html, url="" if is_local else url)

    if not text:
        print("Readability could not extract content from this page.", file=sys.stderr)
        sys.exit(1)

    total_pages = max(1, -(-len(text) // CHARS_PER_PAGE))  # ceil division

    if args.info:
        print(f"Title: {title}")
        print(f"Length: {len(text)} chars")
        print(f"Pages: {total_pages} ({CHARS_PER_PAGE} chars/page)")
        return

    print(f"# {title}\n")

    if args.page is not None:
        if args.page < 1 or args.page > total_pages:
            print(f"Page {args.page} out of range (1-{total_pages})", file=sys.stderr)
            sys.exit(1)
        start = (args.page - 1) * CHARS_PER_PAGE
        end = start + CHARS_PER_PAGE
        print(text[start:end])
        print(f"\n--- Page {args.page}/{total_pages} ---")
    else:
        print(text)
        print(f"\n--- {len(text)} chars, {total_pages} pages ---")


if __name__ == "__main__":
    main()
