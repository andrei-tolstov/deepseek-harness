import json

logfile = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/call_logs/2026-10-14/2026-10-14T17-15-42.345Z_90e8fd.json"

with open(logfile, "r", encoding="utf-8") as f:
    data = json.load(f)

print("SUMMARY:", json.dumps(data.get("summary"), indent=2, ensure_ascii=False))
req_body = data.get("requestBody", {})
print("REQUEST BODY keys:", list(req_body.keys()))
print("Model:", req_body.get("model"))
print("max_tokens:", req_body.get("max_tokens"))
print("max_completion_tokens:", req_body.get("max_completion_tokens"))
print("stream:", req_body.get("stream"))
print("Messages count:", len(req_body.get("messages", [])))

resp_body = data.get("responseBody")
print("\nRESPONSE BODY type:", type(resp_body))
print("RESPONSE BODY preview:", str(resp_body)[:1000])

err = data.get("error")
print("\nERROR:", err)
