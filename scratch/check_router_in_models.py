import urllib.request
import json

req = urllib.request.Request(
    "http://127.0.0.1:20128/v1/models",
    headers={"Authorization": "Bearer sk-cb4c532e2e182bc0-083f70-ef5e4ebe"}
)

try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        models = [m.get("id") for m in data.get("data", [])]
        print(f"Total models with manage key: {len(models)}")
        print("Is andrei-router in models?", "andrei-router" in models)
        for m in models:
            if "andrei" in m:
                print("Found:", m)
except Exception as e:
    print("Error:", e)
