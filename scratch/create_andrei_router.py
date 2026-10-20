import urllib.request
import json

manage_key = "sk-cb4c532e2e182bc0-083f70-ef5e4ebe"

payload = {
    "name": "andrei-router",
    "strategy": "priority",
    "models": [
        "coder390/coder390-27b",
        "qwen38/qwen3.8",
        "fable/fable-cold-fusion-27b"
    ]
}

req = urllib.request.Request(
    "http://127.0.0.1:20128/api/combos",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {manage_key}",
        "Content-Type": "application/json"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as resp:
        print("POST /api/combos status:", resp.status)
        print("Response:", resp.read().decode("utf-8"))
except Exception as e:
    if hasattr(e, "read"):
        print("Error body:", e.read().decode("utf-8"))
    print("Error:", e)
