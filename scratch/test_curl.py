import urllib.request
import urllib.error
import json

payload = {
    "model": "qwen38/qwen3.8-27b",
    "messages": [
        {"role": "system", "content": "You are a bot."},
        {"role": "assistant", "content": "Thinking..."},
        {"role": "tool", "content": "Result 42"}
    ],
    "max_tokens": 10
}
req = urllib.request.Request(
    "http://127.0.0.1:20128/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": "Bearer sk-omniroute"}
)
try:
    with urllib.request.urlopen(req) as resp:
        print("OmniRoute Success:", resp.read().decode()[:300])
except urllib.error.HTTPError as e:
    print("OmniRoute HTTPError:", e.code, e.read().decode())
