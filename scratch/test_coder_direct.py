import urllib.request
import json
import time

url = "http://127.0.0.1:8084/v1/chat/completions"
payload = {
    "model": "coder390-27b",
    "messages": [
        {"role": "user", "content": "Напиши функцию на Python для вычисления факториала и кратко поясни."}
    ],
    "max_tokens": 150,
    "temperature": 0.65
}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

print("Sending request to coder390-llama-server (timeout=180s)...")
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=180) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        latency = time.time() - t0
        print(f"\nDirect Response ({latency:.2f}s):")
        choice = result["choices"][0]["message"]
        if "reasoning_content" in choice and choice["reasoning_content"]:
            print("\n[Thinking/Reasoning]:\n", choice["reasoning_content"])
        print("\n[Content]:\n", choice.get("content"))
        print("\nUsage:", result.get("usage"))
except Exception as e:
    print("Error:", e)
