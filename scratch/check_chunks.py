import glob
import json
import subprocess

session_files = glob.glob("/var/lib/docker/volumes/deepseek_dsh_home/_data/sessions/*/*/session.v4.jsonl.zstd")
chunk_types = set()
finish_reasons = set()
attempts_count = 0

for sf in session_files[:10]:
    proc = subprocess.Popen(["zstd", "-d", "-c", sf], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = proc.communicate()
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        if not line.strip(): continue
        try:
            ev = json.loads(line)
            if ev.get("type") == "assistant/attempt":
                attempts_count += 1
                stream = ev.get("data", {}).get("stream", [])
                for item in stream:
                    ch = item.get("chunk", {})
                    ct = ch.get("type")
                    chunk_types.add(ct)
                    if ct == "finish":
                        finish_reasons.add(str(ch.get("reason")))
        except:
            pass

print(f"Scanned {attempts_count} attempts.")
print("Chunk types:", chunk_types)
print("Finish reasons:", finish_reasons)
