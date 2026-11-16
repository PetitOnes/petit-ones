"""家の中の体(M5)を探す。192.168.1.x を総当たりで /sensor に当たり、返事があった IP を出す。"""
import concurrent.futures
import urllib.request


def check_host(ip):
    try:
        r = urllib.request.urlopen(f'http://{ip}/sensor', timeout=0.4)
        data = r.read(200)
        if b'ambient' in data or b'proximity' in data or b'battery' in data:
            return ip, data[:100].decode('utf-8', errors='replace')
    except Exception:
        pass
    return None

candidates = []
for i in range(1, 255):
    candidates.append(f'10.10.24.{i}')
for sub in range(0, 256):
    for i in range(1, 255):
        ip = f'10.10.{sub}.{i}'
        if ip not in candidates:
            candidates.append(ip)

print(f"Scanning {len(candidates[:2000])} IPs...")
with concurrent.futures.ThreadPoolExecutor(max_workers=200) as ex:
    results = list(ex.map(check_host, candidates[:2000]))

found = [r for r in results if r]
if found:
    for ip, data in found:
        print(f"FOUND: {ip} -> {data}")
else:
    print("Not found in first 2000 IPs")
