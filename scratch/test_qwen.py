import urllib.request
import json

data = {
    "model": "qwen3.8-27b",
    "messages": [
        {"role": "user", "content": "Привет! Ответь одним словом: работает?"}
    ],
    "max_tokens": 16,
    "chat_template_kwargs": {"enable_thinking": False}
}

req = urllib.request.Request(
    "http://127.0.0.1:8081/v1/chat/completions",
    headers={"Content-Type": "application/json"},
    data=json.dumps(data).encode("utf-8")
)

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("Model:", res.get("model"))
        print("Content:", res["choices"][0]["message"].get("content"))
        print("Reasoning:", res["choices"][0]["message"].get("reasoning_content"))
        print("Usage:", res.get("usage"))
except Exception as e:
    print("Error:", e)
