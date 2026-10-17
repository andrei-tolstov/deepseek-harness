import os
import glob
import json
import subprocess

session_files = glob.glob("/var/lib/docker/volumes/deepseek_dsh_home/_data/sessions/*/*/session.v4.jsonl.zstd")
print(f"Found {len(session_files)} session files.")

if session_files:
    sample_file = session_files[0]
    print(f"Sampling: {sample_file}")
    proc = subprocess.Popen(["zstd", "-d", "-c", sample_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = proc.communicate()
    lines = stdout.decode("utf-8", errors="replace").splitlines()
    print(f"Total lines in sample: {len(lines)}")
    types = set()
    sample_events = {}
    for line in lines:
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
            t = ev.get("type")
            types.add(t)
            if t not in sample_events:
                sample_events[t] = ev
        except Exception as e:
            pass
    print("Event types:", sorted(list(types)))
    for t in sorted(list(types)):
        print(f"\n--- TYPE: {t} ---")
        print(json.dumps(sample_events[t], indent=2, ensure_ascii=False)[:500])
