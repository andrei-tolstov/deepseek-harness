import urllib.request
import json

req = urllib.request.Request(
    "http://127.0.0.1:20128/v1/models",
    headers={"Authorization": "Bearer sk-cb4c532e2e182bc0-211cb0-6bac13f5"}
)

with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))

for m in data.get("data", []):
    if "qwen" in m.get("id", "").lower() or "qwen" in m.get("name", "").lower():
        print(json.dumps(m, indent=2, ensure_ascii=False))
