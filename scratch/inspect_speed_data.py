import glob
import json
import subprocess

session_files = glob.glob("/var/lib/docker/volumes/deepseek_dsh_home/_data/sessions/*/*/session.v4.jsonl.zstd")
usages = []

for sf in session_files:
    proc = subprocess.Popen(["zstd", "-d", "-c", sf], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = proc.communicate()
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        if not line.strip(): continue
        try:
            ev = json.loads(line)
            if ev.get("type") == "assistant/attempt":
                stream = ev.get("data", {}).get("stream", [])
                for it in stream:
                    ch = it.get("chunk", {})
                    if ch.get("type") == "usage":
                        usages.append((sf.split("/")[-2], ev.get("seq"), ev.get("time"), ch))
                        if len(usages) >= 10:
                            break
        except Exception:
            pass
    if len(usages) >= 10:
        break

for u in usages:
    print(u)
