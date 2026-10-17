import json
import subprocess
from datetime import datetime

sf = "/var/lib/docker/volumes/deepseek_dsh_home/_data/sessions/--workspace-SmartSwitch--/session-b102c5b1-15f2-4b50-b307-71859748d323/session.v4.jsonl.zstd"

proc = subprocess.Popen(["zstd", "-d", "-c", sf], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
stdout, _ = proc.communicate()
lines = stdout.decode("utf-8", errors="replace").splitlines()

print(f"Total events in session: {len(lines)}")

# Look for titles, request headers, request context, and the last 30 events
headers = []
contexts = []
titles = []
turns = []

for line in lines:
    if not line.strip(): continue
    try:
        ev = json.loads(line)
        t = ev.get("type")
        seq = ev.get("seq")
        time_ms = ev.get("time", 0)
        time_str = datetime.fromtimestamp(time_ms / 1000).strftime('%Y-%m-%d %H:%M:%S') if time_ms else ""

        if t == "session/title":
            titles.append((seq, time_str, ev.get("data", {}).get("title")))
        elif t == "request/header":
            headers.append((seq, time_str, ev.get("data", {}).get("header", {})))
        elif t == "request/context":
            contexts.append((seq, time_str, ev.get("data", {})))
        elif t in ("turn/end", "turn/start", "step/end"):
            turns.append((seq, time_str, t, ev.get("data", {})))
    except Exception as e:
        pass

print("\n--- TITLES ---")
for x in titles:
    print(x)

print("\n--- REQUEST HEADERS (all or last 5) ---")
for x in headers[-5:]:
    seq, t_str, h = x
    cfg = h.get("config", {})
    print(f"Seq: {seq} [{t_str}] | provider: {cfg.get('provider')} | model: {cfg.get('model')} | maxTokens: {cfg.get('maxTokens')} | adapterDefaults: {h.get('adapterDefaults')}")

print("\n--- REQUEST CONTEXTS (last 5) ---")
for x in contexts[-5:]:
    print(x)

print("\n--- LAST 20 EVENTS OF SESSION ---")
for line in lines[-20:]:
    try:
        ev = json.loads(line)
        t = ev.get("type")
        seq = ev.get("seq")
        time_ms = ev.get("time", 0)
        time_str = datetime.fromtimestamp(time_ms / 1000).strftime('%H:%M:%S') if time_ms else ""
        print(f"Seq {seq:4d} | {time_str} | Type: {t} | data keys: {list(ev.get('data', {}).keys())}")
        if t == "turn/end":
            print("   Turn end reason:", ev.get("data", {}).get("reason"))
        elif t == "assistant/attempt":
            stream = ev.get("data", {}).get("stream", [])
            for st in stream:
                ch = st.get("chunk", {})
                if ch.get("type") == "finish":
                    print("   Finish chunk:", ch)
    except:
        pass
