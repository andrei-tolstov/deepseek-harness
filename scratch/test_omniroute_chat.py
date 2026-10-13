import urllib.request
import json

data = {
    "model": "qwen38/qwen3.8",
    "messages": [
        {"role": "user", "content": "Привет! Ответь одним словом: работает?"}
    ],
    "max_tokens": 16,
    "chat_template_kwargs": {"enable_thinking": False}
}

req = urllib.request.Request(
    "http://127.0.0.1:20128/v1/chat/completions",
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer sk-cb4c532e2e182bc0-211cb0-6bac13f5"
    },
    data=json.dumps(data).encode("utf-8")
)

try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("Model:", res.get("model"))
        print("Content:", res["choices"][0]["message"].get("content"))
        print("Usage:", res.get("usage"))
except Exception as e:
    print("Error:", e)
