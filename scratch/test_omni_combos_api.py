import urllib.request
import json

manage_key = "sk-cb4c532e2e182bc0-083f70-ef5e4ebe"

req = urllib.request.Request(
    "http://127.0.0.1:20128/api/combos",
    headers={"Authorization": f"Bearer {manage_key}"}
)

try:
    with urllib.request.urlopen(req) as resp:
        print("GET /api/combos status:", resp.status)
        print("Content:", resp.read().decode("utf-8"))
except Exception as e:
    if hasattr(e, "read"):
        print("Error body:", e.read().decode("utf-8"))
    print("Error:", e)
