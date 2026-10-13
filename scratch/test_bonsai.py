import urllib.request
import json

url = "http://127.0.0.1:20128/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer sk-cb4c532e2e182bc0-211cb0-6bac13f5"
}
data = {
    "model": "bonsai2/bonsai2",
    "messages": [
        {"role": "user", "content": "3 цвета"}
    ],
    "stream": True,
    "max_tokens": 30
}

req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
with urllib.request.urlopen(req, timeout=120) as resp:
    print("STATUS:", resp.status)
    for i in range(10):
        line = resp.readline().decode("utf-8").strip()
        if line:
            print(f"FRAME {i}:", line)
