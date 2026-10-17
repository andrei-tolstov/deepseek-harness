import json
import subprocess
import math

sf = "/var/lib/docker/volumes/deepseek_dsh_home/_data/sessions/--workspace-SmartSwitch--/session-b102c5b1-15f2-4b50-b307-71859748d323/session.v4.jsonl.zstd"

proc = subprocess.Popen(["zstd", "-d", "-c", sf], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
stdout, _ = proc.communicate()
lines = stdout.decode("utf-8", errors="replace").splitlines()

total_chars = 0
msg_count = 0

for line in lines:
    if not line.strip(): continue
    try:
        ev = json.loads(line)
        seq = ev.get("seq", 0)
        if seq >= 3309:
            break
        t = ev.get("type")
        if t in ("user/message", "assistant/message", "system/message", "developer/message", "tool/result"):
            msg_count += 1
            data = ev.get("data", {})
            msg = data.get("message", data)
            content = msg.get("content", [])
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict):
                        total_chars += len(b.get("text", "") or b.get("thinking", "") or json.dumps(b))
    except:
        pass

estimated_tokens = math.ceil(total_chars / 3.5)
print(f"Total messages: {msg_count}")
print(f"Total characters: {total_chars}")
print(f"Estimated tokens (at 3.5 chars/tok): {estimated_tokens}")
print(f"Available for model (180000 - {estimated_tokens} - 4096): {180000 - estimated_tokens - 4096}")
print(f"Available for model (65536 - {estimated_tokens} - 4096): {65536 - estimated_tokens - 4096}")
