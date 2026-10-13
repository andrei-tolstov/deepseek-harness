import urllib.request
import json

url = "http://127.0.0.1:20128/api/compression/preview"
api_key = "sk-cb4c532e2e182bc0-083f70-ef5e4ebe"

# Realistic coding agent payload with tool output, diff, and conversation
sample_payload = {
    "mode": "stacked",
    "messages": [
        {
            "role": "system",
            "content": "You are DeepSeek Harness coding assistant. Follow all user instructions carefully."
        },
        {
            "role": "user",
            "content": "Please check git status and test results, then fix any failing tests in the repository."
        },
        {
            "role": "assistant",
            "content": "I will inspect the git status and run the tests to find what is failing."
        },
        {
            "role": "tool",
            "tool_call_id": "call_123",
            "name": "bash",
            "content": """$ git status
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   src/index.ts
	modified:   src/utils.ts

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	temp.log

no changes added to commit (use "git add" to track)
$ npm test
> project@1.0.0 test
> jest --verbose

 PASS  tests/unit/index.test.ts (2.341 s)
  Index Suite
    ✓ should initialize correctly (15 ms)
    ✓ should handle standard requests (8 ms)
    ✓ should validate configuration (5 ms)

 FAIL  tests/unit/utils.test.ts (3.112 s)
  Utils Suite
    ✓ should format strings (3 ms)
    ✕ should parse markdown links (24 ms)

  ● Utils Suite › should parse markdown links

    expect(received).toEqual(expected)

    - Expected  - 1
    + Received  + 1

    - https://example.com/target
    + https://example.com/wrong

      18 |     const result = parseLink("[test](https://example.com/wrong)");
      19 |     expect(result.url).toEqual("https://example.com/target");
         |                        ^
      20 |   });

Test Suites: 1 failed, 1 passed, 2 total
Tests:       1 failed, 4 passed, 5 total
Snapshots:   0 total
Time:        4.521 s
Ran all test suites."""
        }
    ]
}

req = urllib.request.Request(
    url,
    data=json.dumps(sample_payload).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("=== COMPRESSION PREVIEW RESULTS ===")
        print(f"Original Tokens:   {res.get('originalTokens')}")
        print(f"Compressed Tokens: {res.get('compressedTokens')}")
        print(f"Tokens Saved:      {res.get('tokensSaved')}")
        print(f"Savings Percent:   {res.get('savingsPct')}%")
        print(f"Techniques:        {res.get('techniquesUsed')}")
        print(f"Engine Breakdown:  {res.get('engineBreakdown')}")
        print("\n--- COMPRESSED OUTPUT PREVIEW ---")
        print(res.get('compressed')[:400])
except urllib.error.HTTPError as e:
    print("HTTPError:", e.code, e.read().decode("utf-8"))
except Exception as e:
    print("Error:", e)
