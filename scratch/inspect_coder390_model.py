import urllib.request
import json

api_key = "sk-cb4c532e2e182bc0-bd7c5a-d2a11b99"
req = urllib.request.Request(
    "http://127.0.0.1:20128/v1/models",
    headers={"Authorization": f"Bearer {api_key}"}
)

try:
    resp = urllib.request.urlopen(req)
    payload = json.loads(resp.read().decode("utf-8"))
    for m in payload.get("data", []):
        if "coder390" in m.get("id", ""):
            print("Model Info in OmniRoute:")
            print(json.dumps(m, indent=2, ensure_ascii=False))
except Exception as e:
    print("Error querying OmniRoute:", e)
