import urllib.request
import json
import time

url = "http://127.0.0.1:8082/v1/chat/completions"
payload = {
    "model": "bonsai2",
    "messages": [
        {"role": "user", "content": "Write a 300 word essay about the history of artificial intelligence."}
    ],
    "max_tokens": 250,
    "temperature": 0.7
}
data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

t0 = time.time()
with urllib.request.urlopen(req) as resp:
    res = json.loads(resp.read().decode("utf-8"))
dt = time.time() - t0

usage = res.get("usage", {})
print(f"Elapsed: {dt:.2f}s")
print(f"Usage: {usage}")
if "choices" in res and len(res["choices"]) > 0:
    content = res["choices"][0]["message"].get("content", "")
    print(f"Generated text length: {len(content)} chars")
    print("Preview:", content[:100].replace("\n", " "))
    tps = usage.get("completion_tokens", 0) / dt if dt > 0 else 0
    print(f"Throughput: {tps:.2f} tokens/sec")
