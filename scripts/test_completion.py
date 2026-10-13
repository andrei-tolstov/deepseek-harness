import urllib.request
import json
import time

url = "http://127.0.0.1:8082/completion"
payload = {
    "prompt": "<|im_start|>user\nWrite a quick sentence.<|im_end|>\n<|im_start|>assistant\n",
    "n_predict": 100,
    "temperature": 0.7,
    "stream": False
}
req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
t0 = time.time()
with urllib.request.urlopen(req) as resp:
    res = json.loads(resp.read().decode("utf-8"))
dt = time.time() - t0
print(f"Elapsed: {dt:.2f}s")
print("Content:", repr(res.get("content", "")))
print("Timings:", json.dumps(res.get("timings", {}), indent=2))
