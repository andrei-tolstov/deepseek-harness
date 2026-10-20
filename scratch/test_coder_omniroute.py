import urllib.request
import json
import time

url = "http://127.0.0.1:20128/v1/chat/completions"
api_key = "sk-cb4c532e2e182bc0-bd7c5a-d2a11b99"
payload = {
    "model": "coder390/coder390-27b",
    "messages": [
        {"role": "user", "content": "Привет! Назови 3 преимущества языка Rust."}
    ],
    "max_tokens": 150,
    "temperature": 0.65
}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
)

print("Sending request through OmniRoute to coder390/coder390-27b...")
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        latency = time.time() - t0
        print(f"\nOmniRoute Response ({latency:.2f}s):")
        choice = result["choices"][0]["message"]
        if "reasoning_content" in choice and choice["reasoning_content"]:
            print("\n[Thinking/Reasoning]:\n", choice["reasoning_content"])
        print("\n[Content]:\n", choice.get("content"))
        print("\nModel Used:", result.get("model"))
        print("Usage:", result.get("usage"))
except Exception as e:
    if hasattr(e, "read"):
        print("Error Body:", e.read().decode("utf-8", errors="replace"))
    print("Error:", e)
