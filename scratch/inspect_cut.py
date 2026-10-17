import json
import subprocess

sf = "/var/lib/docker/volumes/deepseek_dsh_home/_data/sessions/--workspace-SmartSwitch--/session-b102c5b1-15f2-4b50-b307-71859748d323/session.v4.jsonl.zstd"

proc = subprocess.Popen(["zstd", "-d", "-c", sf], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
stdout, _ = proc.communicate()
lines = stdout.decode("utf-8", errors="replace").splitlines()

for line in lines:
    if not line.strip(): continue
    try:
        ev = json.loads(line)
        seq = ev.get("seq")
        if seq in (3312, 3313, 3314, 3319, 3320):
            print(f"\n================ EVENT SEQ {seq} ================")
            print("Type:", ev.get("type"))
            if seq == 3312:
                # inspect assistant/message
                data = ev.get("data", {})
                print("Usage in data:", data.get("usage"))
                stream = data.get("stream", [])
                print("Stream length:", len(stream))
                for st in stream:
                    ch = st.get("chunk", {})
                    if ch.get("type") in ("finish", "usage"):
                        print("Stream chunk:", ch)
                # length of content
                msg = data.get("message", {})
                content = msg.get("content", [])
                for b in content:
                    btype = b.get("type")
                    text = b.get("text", "")
                    print(f"Content block [{btype}]: len={len(text)} chars | preview: {text[:150]}...")
            elif seq == 3320:
                print("Compaction end error:", ev.get("data", {}).get("error"))
            else:
                print("Data:", ev.get("data"))
    except:
        pass
