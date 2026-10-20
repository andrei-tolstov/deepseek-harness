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
    all_models = [m.get("id") for m in payload.get("data", [])]
    relevant_models = [m for m in all_models if any(k in m for k in ["coder390", "fable", "qwen38", "andrei", "router"])]
    print(f"Total models returned by OmniRoute: {len(all_models)}")
    print("Relevant local models:")
    for m in relevant_models:
        print(" -", m)
except Exception as e:
    print("Error querying OmniRoute:", e)
