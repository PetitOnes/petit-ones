import concurrent.futures
import urllib.request
import socket

def check_host(ip):
    try:
        r = urllib.request.urlopen(f'http://{ip}/sensor', timeout=0.5)
        data = r.read(200)
        if b'ambient' in data or b'proximity' in data or b'battery' in data:
            return ip, data[:120].decode('utf-8', errors='replace')
    except:
        pass
    return None

def check_host_root(ip):
    try:
        r = urllib.request.urlopen(f'http://{ip}/', timeout=0.5)
        data = r.read(200)
        return ip, data[:80].decode('utf-8', errors='replace')
    except:
        pass
    return None

candidates = [f'10.10.{sub}.{i}' for sub in range(0, 256) for i in range(1, 255)]
start = 2000
end = min(start + 4000, len(candidates))
chunk = candidates[start:end]
print(f"Scanning {len(chunk)} more IPs ({chunk[0]} - {chunk[-1]})...")
with concurrent.futures.ThreadPoolExecutor(max_workers=300) as ex:
    results = list(ex.map(check_host, chunk))

found = [r for r in results if r]
if found:
    for ip, data in found:
        print(f"FOUND: {ip} -> {data}")
else:
    print("Not found in this range either")
