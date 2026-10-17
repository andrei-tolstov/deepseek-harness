import glob
import json
import subprocess

session_files = glob.glob("/var/lib/docker/volumes/deepseek_dsh_home/_data/sessions/*/*/session.v4.jsonl.zstd")
found_msg = []
found_att = []
found_step_end = []

for sf in session_files:
    proc = subprocess.Popen(["zstd", "-d", "-c", sf], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = proc.communicate()
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        if not line.strip(): continue
        try:
            ev = json.loads(line)
            t = ev.get("type")
            if t == "assistant/message" and len(found_msg) < 3:
                found_msg.append(ev)
            elif t == "assistant/attempt" and len(found_att) < 3:
                found_att.append(ev)
            elif t == "step/end" and len(found_step_end) < 3:
                found_step_end.append(ev)
        except:
            pass
    if len(found_msg) >= 3 and len(found_att) >= 3:
        break

print("=== ASSISTANT MESSAGE SAMPLES ===")
for m in found_msg:
    print(json.dumps(m, indent=2, ensure_ascii=False)[:800])
    print("-" * 50)

print("=== ASSISTANT ATTEMPT SAMPLES ===")
for a in found_att:
    print(json.dumps(a, indent=2, ensure_ascii=False)[:800])
    print("-" * 50)

print("=== STEP END SAMPLES ===")
for s in found_step_end:
    print(json.dumps(s, indent=2, ensure_ascii=False)[:800])
    print("-" * 50)
