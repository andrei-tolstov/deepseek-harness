import json
import subprocess

sf = "/var/lib/docker/volumes/deepseek_dsh_home/_data/sessions/--workspace-SmartSwitch--/session-b102c5b1-15f2-4b50-b307-71859748d323/session.v4.jsonl.zstd"

proc = subprocess.Popen(["zstd", "-d", "-c", sf], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
stdout, _ = proc.communicate()
lines = stdout.decode("utf-8", errors="replace").splitlines()

# Find the request around seq 3309 and inspect previous assistant usage
last_assistant_usage = None
total_messages_chars = 0
assistant_count = 0

for line in lines:
    if not line.strip(): continue
    try:
        ev = json.loads(line)
        seq = ev.get("seq", 0)
        if seq >= 3309:
            break
        if ev.get("type") == "assistant/message":
            assistant_count += 1
            u = ev.get("data", {}).get("usage")
            if u:
                last_assistant_usage = (seq, u)
    except:
        pass

print("Last assistant usage before seq 3309:", last_assistant_usage)
print("Total assistant messages before seq 3309:", assistant_count)
