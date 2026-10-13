import urllib.request
import json
import time

print("Testing llama-server connection...")
req = urllib.request.Request(
    'http://127.0.0.1:8082/completion',
    data=json.dumps({'prompt': 'Explain quantum computing in one sentence:', 'n_predict': 50}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
t0 = time.time()
with urllib.request.urlopen(req) as resp:
    res = json.loads(resp.read().decode('utf-8'))
dt = time.time() - t0
print(f"Elapsed: {dt:.2f}s")
print("Response text:", res.get("content"))
print("Timings:", json.dumps(res.get("timings"), indent=2))
