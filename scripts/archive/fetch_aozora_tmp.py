import urllib.request
import re
import sys

url = 'https://www.aozora.gr.jp/cards/000026/files/219_33152.html'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as f:
    html = f.read().decode('shift_jis', errors='replace')

text = re.sub(r'<ruby><rb>(.*?)</rb><rp>.*?</rp><rt>.*?</rt><rp>.*?</rp></ruby>', r'\1', html, flags=re.DOTALL)
text = re.sub(r'<[^>]+>', '', text)
text = re.sub(r'&nbsp;', ' ', text)
text = re.sub(r'&amp;', '&', text)
text = re.sub(r'\n{3,}', '\n\n', text)

start = text.find('含羞')
end = text.find('底本：')
if start > 0 and end > 0:
    chunk = text[start:end]
else:
    chunk = text[2000:12000]

offset = int(sys.argv[1]) if len(sys.argv) > 1 else 0
print(chunk[offset:offset+6000])
