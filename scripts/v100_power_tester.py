import subprocess
import time
import re
import json
import sys

def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout.strip()

def get_telemetry():
    out = run_cmd("nvidia-smi --query-gpu=power.draw,temperature.gpu,clocks.current.graphics,clocks.current.sm,clocks.current.memory,utilization.gpu --format=csv,noheader,nounits")
    parts = [p.strip() for p in out.split(",")]
    if len(parts) >= 6:
        return {
            "power": float(parts[0]),
            "temp": float(parts[1]),
            "clock_graphics": float(parts[2]),
            "clock_sm": float(parts[3]),
            "clock_mem": float(parts[4]),
            "util": float(parts[5])
        }
    return None

def get_current_tps():
    out = run_cmd("docker logs --tail 6 bonsai2-llama-server")
    matches = re.findall(r"tg_3s\s*=\s*([0-9.]+)\s*t/s", out)
    if matches:
        return float(matches[-1])
    matches2 = re.findall(r"tg\s*=\s*([0-9.]+)\s*t/s", out)
    if matches2:
        return float(matches2[-1])
    return None

def reset_gpu():
    print("[*] Resetting GPU to defaults (250W, unlocked clocks)...")
    run_cmd("nvidia-smi -rgc")
    run_cmd("nvidia-smi -pl 250")
    time.sleep(2)

def benchmark_profile(name, setup_cmds, duration=20, settle_time=6):
    print(f"\n=======================================================")
    print(f"[*] Applying profile: {name}")
    for cmd in setup_cmds:
        print(f"    Exec: {cmd}")
        run_cmd(cmd)
    
    print(f"[*] Settling for {settle_time}s...")
    time.sleep(settle_time)
    
    # Launch gemm_bench to guarantee full Tensor-Core saturation throughout the test window
    print(f"[*] Launching GEMM benchmark for {duration}s...")
    gemm_proc = subprocess.Popen(
        f"/root/gemm_bench {duration}",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    powers = []
    temps = []
    clocks = []
    tps_list = []
    
    t_end = time.time() + duration + 5
    while gemm_proc.poll() is None and time.time() < t_end:
        t0 = time.time()
        telem = get_telemetry()
        tps = get_current_tps()
        
        if telem:
            powers.append(telem["power"])
            temps.append(telem["temp"])
            clocks.append(telem["clock_graphics"])
        if tps is not None and tps > 5.0:
            tps_list.append(tps)
            
        cur_p = telem["power"] if telem else 0.0
        cur_t = telem["temp"] if telem else 0.0
        cur_c = telem["clock_graphics"] if telem else 0.0
        cur_tps = tps if tps else 0.0
        print(f"    [Sample] Pwr: {cur_p:5.1f}W | Temp: {cur_t:2.0f}C | Clock: {cur_c:4.0f}MHz | TPS: {cur_tps:4.1f} t/s", flush=True)
        
        rem = 1.0 - (time.time() - t0)
        if rem > 0:
            time.sleep(rem)
            
    gemm_out, _ = gemm_proc.communicate()
    tflops_match = re.search(r"TFLOPS=([0-9.]+)", gemm_out)
    tflops = float(tflops_match.group(1)) if tflops_match else 0.0
    
    avg_pwr = sum(powers) / len(powers) if powers else 0.0
    avg_temp = sum(temps) / len(temps) if temps else 0.0
    max_temp = max(temps) if temps else 0.0
    avg_clock = sum(clocks) / len(clocks) if clocks else 0.0
    avg_tps = sum(tps_list) / len(tps_list) if tps_list else 0.0
    efficiency = (tflops / avg_pwr) if avg_pwr > 0 else 0.0
    
    result = {
        "profile": name,
        "avg_power_w": round(avg_pwr, 2),
        "avg_temp_c": round(avg_temp, 1),
        "max_temp_c": round(max_temp, 1),
        "avg_clock_mhz": round(avg_clock, 1),
        "tflops": round(tflops, 2),
        "avg_tps": round(avg_tps, 2),
        "eff_tflops_per_w": round(efficiency, 4),
        "samples_count": len(powers)
    }
    print(f"[*] Done {name}: Pwr={result['avg_power_w']}W, Temp={result['avg_temp_c']}C, Clock={result['avg_clock_mhz']}MHz, TFLOPS={result['tflops']}, TPS={result['avg_tps']} t/s, Eff={result['eff_tflops_per_w']} TFLOPS/W")
    return result

def main():
    try:
        reset_gpu()
        
        profiles = [
            # 1. Power Limit Scaling
            ("PowerLimit 250W (Stock)", ["nvidia-smi -rgc", "nvidia-smi -pl 250"]),
            ("PowerLimit 220W", ["nvidia-smi -pl 220"]),
            ("PowerLimit 190W", ["nvidia-smi -pl 190"]),
            ("PowerLimit 160W", ["nvidia-smi -pl 160"]),
            ("PowerLimit 130W", ["nvidia-smi -pl 130"]),
            ("PowerLimit 100W (Min)", ["nvidia-smi -pl 100"]),
            
            # 2. Clock Locking / Undervolting via -lgc
            ("ClockLock 1380MHz (Stock Boost)", ["nvidia-smi -pl 250", "nvidia-smi -lgc 1380,1380"]),
            ("ClockLock 1260MHz (UV-Mild)", ["nvidia-smi -lgc 1260,1260"]),
            ("ClockLock 1140MHz (UV-Medium)", ["nvidia-smi -lgc 1140,1140"]),
            ("ClockLock 1020MHz (UV-High)", ["nvidia-smi -lgc 1020,1020"]),
            ("ClockLock 900MHz (UV-Maximum)", ["nvidia-smi -lgc 900,900"]),
        ]
        
        results = []
        for name, cmds in profiles:
            res = benchmark_profile(name, cmds, duration=20, settle_time=6)
            results.append(res)
            
        with open("/root/v100_benchmark_results.json", "w") as f:
            json.dump(results, f, indent=2)
            
        print("\n\nAll tests completed successfully. JSON saved to /root/v100_benchmark_results.json")
    finally:
        reset_gpu()

if __name__ == "__main__":
    main()
