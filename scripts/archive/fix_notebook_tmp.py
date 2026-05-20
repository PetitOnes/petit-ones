import json

path = '/home/cube-petit/petit_claude/exchange_notebook.json'
with open(path) as f:
    data = json.load(f)

last = data[-1]
print(f"Last: [{last['author']}] {last['date']} / {last['content'][:50]}")

if last['author'] == 'ぷちこ' and last['date'] == '2026/03/25 12:46':
    data = data[:-1]
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'Removed. Total now: {len(data)}')
else:
    print('No match - nothing done')
