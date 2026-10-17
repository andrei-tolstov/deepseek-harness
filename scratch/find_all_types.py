import glob
import json
import subprocess

session_files = glob.glob("/var/lib/docker/volumes/deepseek_dsh_home/_data/sessions/*/*/session.v4.jsonl.zstd")
all_types = set()
for sf in session_files:
    proc = subprocess.Popen(["zstd", "-d", "-c", sf], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = proc.communicate()
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        if not line.strip(): continue
        try:
            ev = json.loads(line)
            all_types.add(ev.get("type"))
        except:
            pass

print("ALL EVENT TYPES ACROSS ALL SESSIONS:")
for t in sorted(list(all_types)):
    print(" -", t)
