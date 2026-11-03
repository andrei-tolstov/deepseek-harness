import urllib.request
import subprocess
import time
import json
import re
import sys
import os

def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout.strip()

def get_v100_uuid():
    try:
        out = run_cmd("nvidia-smi --query-gpu=uuid,name --format=csv,noheader")
        for line in out.splitlines():
            if "v100" in line.lower():
                return line.split(",")[0].strip()
    except Exception:
        pass
    return os.environ.get("TARGET_GPU_UUID", "GPU-733ae7cc-c1bf-3352-42d5-ba2762470325")

TARGET_GPU = get_v100_uuid()

def get_telemetry():
    out = run_cmd(f"nvidia-smi -i {TARGET_GPU} --query-gpu=power.draw,temperature.gpu,clocks.current.graphics,clocks.current.sm,clocks.current.memory,utilization.gpu --format=csv,noheader,nounits")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if lines:
        parts = [p.strip() for p in lines[0].split(",")]
        if len(parts) >= 6:
            try:
                return {
                    "power": float(parts[0]),
                    "temp": float(parts[1]),
                    "clock_graphics": float(parts[2]),
                    "clock_sm": float(parts[3]),
                    "clock_mem": float(parts[4]),
                    "util": float(parts[5])
                }
            except ValueError:
                pass
    return None

def reset_gpu():
    print(f"[*] Resetting GPU {TARGET_GPU} to stock defaults (250W, unlocked clocks)...")
    run_cmd(f"nvidia-smi -i {TARGET_GPU} -rgc")
    run_cmd(f"nvidia-smi -i {TARGET_GPU} -pl 250")
    time.sleep(2)

def test_llm_run(name, setup_cmds, n_predict=350):
    print(f"\n=======================================================")
    print(f"[*] Testing LLM Inference for profile: {name}")
    for cmd in setup_cmds:
        actual_cmd = f"nvidia-smi -i {TARGET_GPU} " + cmd if not cmd.startswith("nvidia-smi -i") else cmd
        run_cmd(actual_cmd)
    time.sleep(4)
    
    # Payload for OpenAI chat completions on llama-swap (port 8090) or coder390 (8084)
    url = os.environ.get("INFERENCE_URL", "http://127.0.0.1:8090/v1/chat/completions")
    payload = {
        "model": "coder390",
        "messages": [
            {
                "role": "user",
                "content": "Explain in detail the fundamental differences between quantum annealing and gate-based quantum computing, including hardware implementations, error mitigation, and suitable problem classes."
            }
        ],
        "max_tokens": n_predict,
        "temperature": 0.7,
        "stream": False
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    # Warmup / check connectivity
    t_start = time.time()
    telemetry_samples = []
    
    print("[*] Sending inference request...")
    try:
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        total_time = time.time() - t0
    except Exception as e:
        print(f"[!] Error during inference request to {url}: {e}")
        return None
        
    t_telemetry_end = time.time()
    t = get_telemetry()
    if t:
        telemetry_samples.append(t)
        
    usage = data.get("usage", {})
    comp_tokens = usage.get("completion_tokens", 0)
    prompt_tokens = usage.get("prompt_tokens", 0)
    
    tps = comp_tokens / total_time if total_time > 0 else 0.0
    
    # Measure average power during prompt/generation
    avg_power = t["power"] if t else 0.0
    tokens_per_watt = tps / avg_power if avg_power > 0 else 0.0
    
    res = {
        "profile": name,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": comp_tokens,
        "total_time_s": round(total_time, 2),
        "tps": round(tps, 2),
        "power_w": round(avg_power, 1),
        "temp_c": round(t["temp"], 1) if t else 0.0,
        "clock_mhz": round(t["clock_graphics"], 0) if t else 0.0,
        "tokens_per_watt": round(tokens_per_watt, 3)
    }
    
    print(f"[+] Output: {comp_tokens} tokens in {res['total_time_s']}s -> Speed: {res['tps']} t/s")
    print(f"    Power:  {res['power_w']} W | Temp: {res['temp_c']} °C | Clock: {res['clock_mhz']} MHz")
    print(f"    Efficiency: {res['tokens_per_watt']} tokens/Watt")
    
    return res

def main():
    print(f"[*] Starting Tesla V100 LLM Real-World Inference Benchmark on {TARGET_GPU}")
    reset_gpu()
    
    profiles = [
        ("Stock (250W Auto)", [f"nvidia-smi -i {TARGET_GPU} -rgc", f"nvidia-smi -i {TARGET_GPU} -pl 250"]),
        ("Cap 200W Auto", [f"nvidia-smi -i {TARGET_GPU} -rgc", f"nvidia-smi -i {TARGET_GPU} -pl 200"]),
        ("Cap 160W Auto", [f"nvidia-smi -i {TARGET_GPU} -rgc", f"nvidia-smi -i {TARGET_GPU} -pl 160"]),
        ("Lock 1380MHz (250W)", [f"nvidia-smi -i {TARGET_GPU} -lgc 1380", f"nvidia-smi -i {TARGET_GPU} -pl 250"]),
        ("Lock 1245MHz (200W)", [f"nvidia-smi -i {TARGET_GPU} -lgc 1245", f"nvidia-smi -i {TARGET_GPU} -pl 200"]),
        ("Lock 1132MHz (160W)", [f"nvidia-smi -i {TARGET_GPU} -lgc 1132", f"nvidia-smi -i {TARGET_GPU} -pl 160"]),
        ("Lock 997MHz (140W)", [f"nvidia-smi -i {TARGET_GPU} -lgc 997", f"nvidia-smi -i {TARGET_GPU} -pl 140"]),
        ("Lock 855MHz (110W)", [f"nvidia-smi -i {TARGET_GPU} -lgc 855", f"nvidia-smi -i {TARGET_GPU} -pl 110"]),
        ("Lock 495MHz (100W Night)", [f"nvidia-smi -i {TARGET_GPU} -lgc 495", f"nvidia-smi -i {TARGET_GPU} -pl 100"]),
    ]
    
    results = []
    try:
        for name, cmds in profiles:
            r = test_llm_run(name, cmds, n_predict=300)
            if r:
                results.append(r)
            time.sleep(3)
    finally:
        reset_gpu()
        
    print("\n\n=======================================================")
    print("FINAL LLM INFERENCE BENCHMARK SUMMARY")
    print("=======================================================")
    print("| Profile | Speed (t/s) | Power (W) | Temp (°C) | Clock (MHz) | Tokens / Watt |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for r in results:
        print(f"| {r['profile']} | {r['tps']} | {r['power_w']} W | {r['temp_c']} °C | {r['clock_mhz']} MHz | {r['tokens_per_watt']} |")

if __name__ == "__main__":
    main()
