import subprocess
import time
import re
import json
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

def get_current_tps():
    out = run_cmd("docker logs --tail 6 coder390-llama-server 2>/dev/null || docker logs --tail 6 bonsai2-llama-server 2>/dev/null")
    matches = re.findall(r"decode\s*([0-9.]+)\s*tok/s", out)
    if matches:
        return float(matches[-1])
    matches_tg = re.findall(r"tg_3s\s*=\s*([0-9.]+)\s*t/s", out)
    if matches_tg:
        return float(matches_tg[-1])
    return None

def reset_gpu():
    print(f"[*] Resetting GPU {TARGET_GPU} to defaults (250W, unlocked clocks)...")
    run_cmd(f"nvidia-smi -i {TARGET_GPU} -rgc")
    run_cmd(f"nvidia-smi -i {TARGET_GPU} -pl 250")
    time.sleep(2)

def benchmark_profile(name, setup_cmds, duration=20, settle_time=6):
    print(f"\n=======================================================")
    print(f"[*] Applying profile: {name}")
    for cmd in setup_cmds:
        actual_cmd = f"nvidia-smi -i {TARGET_GPU} " + cmd if not cmd.startswith("nvidia-smi -i") else cmd
        print(f"    Exec: {actual_cmd}")
        run_cmd(actual_cmd)
    
    print(f"[*] Settling for {settle_time}s...")
    time.sleep(settle_time)
    
    samples = []
    t_end = time.time() + duration
    while time.time() < t_end:
        t = get_telemetry()
        if t:
            tps = get_current_tps()
            if tps:
                t["tps"] = tps
            samples.append(t)
        time.sleep(0.5)
        
    if not samples:
        print("[!] No telemetry collected!")
        return None
        
    avg_power = sum(s["power"] for s in samples) / len(samples)
    max_power = max(s["power"] for s in samples)
    avg_temp = sum(s["temp"] for s in samples) / len(samples)
    max_temp = max(s["temp"] for s in samples)
    avg_clk = sum(s["clock_graphics"] for s in samples) / len(samples)
    
    tps_samples = [s["tps"] for s in samples if "tps" in s]
    avg_tps = sum(tps_samples) / len(tps_samples) if tps_samples else 0.0
    
    efficiency = avg_tps / avg_power if avg_power > 0 else 0.0
    
    res = {
        "profile": name,
        "avg_power_w": round(avg_power, 1),
        "max_power_w": round(max_power, 1),
        "avg_temp_c": round(avg_temp, 1),
        "max_temp_c": round(max_temp, 1),
        "avg_clock_mhz": round(avg_clk, 0),
        "avg_tps": round(avg_tps, 2),
        "tokens_per_watt": round(efficiency, 3)
    }
    
    print(f"[+] Result for {name}:")
    print(f"    Avg Power: {res['avg_power_w']} W (Max: {res['max_power_w']} W)")
    print(f"    Avg Temp:  {res['avg_temp_c']} °C (Max: {res['max_temp_c']} °C)")
    print(f"    Avg Clock: {res['avg_clock_mhz']} MHz")
    print(f"    Speed:     {res['avg_tps']} t/s")
    print(f"    Efficiency:{res['tokens_per_watt']} tokens/W")
    
    return res

def main():
    print(f"[*] Starting Tesla V100 GPU Power/Clock Benchmark on {TARGET_GPU}")
    reset_gpu()
    
    profiles = [
        ("Stock (250W Auto)", [f"nvidia-smi -i {TARGET_GPU} -rgc", f"nvidia-smi -i {TARGET_GPU} -pl 250"]),
        ("Cap 200W Auto", [f"nvidia-smi -i {TARGET_GPU} -rgc", f"nvidia-smi -i {TARGET_GPU} -pl 200"]),
        ("Cap 180W Auto", [f"nvidia-smi -i {TARGET_GPU} -rgc", f"nvidia-smi -i {TARGET_GPU} -pl 180"]),
        ("Cap 160W Auto", [f"nvidia-smi -i {TARGET_GPU} -rgc", f"nvidia-smi -i {TARGET_GPU} -pl 160"]),
        ("Lock 1380MHz (Max Boost)", [f"nvidia-smi -i {TARGET_GPU} -lgc 1380", f"nvidia-smi -i {TARGET_GPU} -pl 250"]),
        ("Lock 1245MHz (Undervolt High)", [f"nvidia-smi -i {TARGET_GPU} -lgc 1245", f"nvidia-smi -i {TARGET_GPU} -pl 200"]),
        ("Lock 1132MHz (Optimal Efficiency)", [f"nvidia-smi -i {TARGET_GPU} -lgc 1132", f"nvidia-smi -i {TARGET_GPU} -pl 160"]),
        ("Lock 997MHz (Quiet High Perf)", [f"nvidia-smi -i {TARGET_GPU} -lgc 997", f"nvidia-smi -i {TARGET_GPU} -pl 140"]),
        ("Lock 855MHz (Ultra Quiet)", [f"nvidia-smi -i {TARGET_GPU} -lgc 855", f"nvidia-smi -i {TARGET_GPU} -pl 110"]),
        ("Lock 495MHz (Minimum Night)", [f"nvidia-smi -i {TARGET_GPU} -lgc 495", f"nvidia-smi -i {TARGET_GPU} -pl 100"]),
    ]
    
    results = []
    try:
        for name, cmds in profiles:
            r = benchmark_profile(name, cmds, duration=15, settle_time=4)
            if r:
                results.append(r)
    finally:
        reset_gpu()
        
    print("\n\n=======================================================")
    print("FINAL BENCHMARK SUMMARY (MARKDOWN TABLE)")
    print("=======================================================")
    print("| Profile | Avg Power (W) | Avg Temp (°C) | Clock (MHz) | Speed (t/s) | Tokens / Watt |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for r in results:
        print(f"| {r['profile']} | {r['avg_power_w']} W | {r['avg_temp_c']} °C | {r['avg_clock_mhz']} MHz | {r['avg_tps']} | {r['tokens_per_watt']} |")

if __name__ == "__main__":
    main()
