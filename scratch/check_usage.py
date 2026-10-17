import glob
import json
import subprocess

session_files = glob.glob("/var/lib/docker/volumes/deepseek_dsh_home/_data/sessions/*/*/session.v4.jsonl.zstd")
samples_with_usage = []

for sf in session_files:
    proc = subprocess.Popen(["zstd", "-d", "-c", sf], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = proc.communicate()
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        if not line.strip(): continue
        try:
            ev = json.loads(line)
            if ev.get("type") == "assistant/attempt":
                stream = ev.get("data", {}).get("stream", [])
                for item in stream:
                    ch = item.get("chunk", {})
                    if ch.get("type") == "usage":
                        u = ch.get("usage", {})
                        if u.get("outputTokens", 0) > 0:
                            samples_with_usage.append((sf, ev.get("seq"), u))
                            if len(samples_with_usage) >= 5:
                                break
        except:
            pass
    if len(samples_with_usage) >= 5:
        break

print(f"Found {len(samples_with_usage)} usage samples:")
for s in samples_with_usage:
    print(s)
