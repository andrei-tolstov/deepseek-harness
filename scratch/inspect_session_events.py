import glob
import json
import subprocess

session_files = sorted(glob.glob("/var/lib/docker/volumes/deepseek_dsh_home/_data/sessions/*/*/session.v4.jsonl.zstd"))

for sf in session_files:
    if "SmartSwitch" not in sf: continue
    proc = subprocess.Popen(["zstd", "-d", "-c", sf], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = proc.communicate()
    events = []
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        if not line.strip(): continue
        try:
            ev = json.loads(line)
            events.append(ev)
        except:
            pass
    
    # print events summary
    print(f"Session {sf}: {len(events)} events")
    for ev in events[:20]:
        t = ev.get("type")
        seq = ev.get("seq")
        time = ev.get("time")
        if t in ("user/message", "step/start", "step/end", "assistant/attempt", "assistant/message"):
            print(f"  seq={seq} type={t} time={time}")
            if t == "assistant/attempt":
                data = ev.get("data", {})
                stream = data.get("stream", [])
                print(f"    stream items: {len(stream)}")
                for s in stream:
                    ch = s.get("chunk", {})
                    print(f"      chunk type={ch.get('type')} time={s.get('time')}")
    break
