import urllib.request
import json

url = "http://127.0.0.1:20128/api/compression/preview"
api_key = "sk-cb4c532e2e182bc0-083f70-ef5e4ebe"

payload = {
    "mode": "stacked",
    "messages": [
        {"role": "user", "content": "Please run the test suite and check results."},
        {"role": "assistant", "content": "Running tests..."},
        {"role": "user", "content": "$ npm test\n> jest\n\nPASS src/a.test.ts (2.1s)\nPASS src/b.test.ts (1.8s)\nTest Suites: 2 passed, 2 total\nTests: 10 passed, 10 total\nSnapshots: 0 total\nTime: 3.9s\nRan all test suites."}
    ]
}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as resp:
        print("Status:", resp.status)
        print("Response:", json.loads(resp.read().decode("utf-8")))
except urllib.error.HTTPError as e:
    print("HTTPError:", e.code, e.read().decode("utf-8"))
except Exception as e:
    print("Error:", e)
