import urllib.request, re, sys

url = 'https://www.aozora.gr.jp/cards/000081/files/47027_37961.html'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as r:
    d = r.read()

text = d.decode('shift_jis', errors='replace')
text = re.sub(r'<[^>]+>', '', text)
text = re.sub(r'&nbsp;', ' ', text)
text = re.sub(r'&amp;', '&', text)

keyword = sys.argv[1] if len(sys.argv) > 1 else '郊外'
length = int(sys.argv[2]) if len(sys.argv) > 2 else 5000

idx = text.find(keyword)
if idx >= 0:
    print(text[idx:idx+length])
else:
    print(f'"{keyword}" not found')
    # Show all poem-like headers
    for m in re.finditer(r'\n\s{0,5}(.{2,30})\n\s{0,5}一九二四', text):
        print(repr(m.group().strip()[:80]))
