import urllib.request
import subprocess
import time
import json
import re
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

def reset_gpu():
    print("[*] Resetting GPU to stock defaults (250W, unlocked clocks)...")
    run_cmd("nvidia-smi -rgc")
    run_cmd("nvidia-smi -pl 250")
    time.sleep(2)

def test_llm_run(name, setup_cmds, n_predict=350):
    print(f"\n=======================================================")
    print(f"[*] Testing LLM Inference for profile: {name}")
    for cmd in setup_cmds:
        run_cmd(cmd)
    time.sleep(4)
    
    # Payload for completion with reasoning enabled or direct prompt
    url = "http://127.0.0.1:8082/completion"
    prompt = (
        "<|im_start|>user\n"
        "Explain in detail the fundamental differences between quantum annealing and gate-based quantum computing, including hardware implementations, error mitigation, and suitable problem classes.\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    payload = {
        "prompt": prompt,
        "n_predict": n_predict,
        "temperature": 0.7,
        "stream": False
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    # We will poll telemetry in a background thread or sampler while request is executing
    import threading
    telems = []
    stop_event = threading.Event()
    
    def monitor():
        while not stop_event.is_set():
            t = get_telemetry()
            if t:
                telems.append(t)
            time.sleep(0.5)
            
    mon_thread = threading.Thread(target=monitor)
    mon_thread.start()
    
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            result_json = json.loads(raw)
    except Exception as e:
        print(f"[-] Request failed: {e}")
        stop_event.set()
        mon_thread.join()
        return None
        
    t_total = time.time() - t0
    stop_event.set()
    mon_thread.join()
    
    timings = result_json.get("timings", {})
    prompt_n = timings.get("prompt_n", 0)
    prompt_ms = timings.get("prompt_ms", 0)
    pp_speed = timings.get("prompt_per_second", 0.0)
    
    pred_n = timings.get("predicted_n", 0)
    pred_ms = timings.get("predicted_ms", 0)
    tg_speed = timings.get("predicted_per_second", 0.0)
    
    powers = [x["power"] for x in telems] if telems else [0.0]
    temps = [x["temp"] for x in telems] if telems else [0.0]
    clocks = [x["clock_graphics"] for x in telems] if telems else [0.0]
    
    avg_pwr = sum(powers) / len(powers) if powers else 0.0
    avg_temp = sum(temps) / len(temps) if temps else 0.0
    max_temp = max(temps) if temps else 0.0
    avg_clock = sum(clocks) / len(clocks) if clocks else 0.0
    
    eff_tokens_per_joule = (pred_n / (avg_pwr * (pred_ms / 1000.0))) if (avg_pwr > 0 and pred_ms > 0) else 0.0
    
    res = {
        "profile": name,
        "avg_power_w": round(avg_pwr, 1),
        "avg_temp_c": round(avg_temp, 1),
        "max_temp_c": round(max_temp, 1),
        "avg_clock_mhz": round(avg_clock, 1),
        "prompt_tokens": prompt_n,
        "prompt_speed_tps": round(pp_speed, 1),
        "gen_tokens": pred_n,
        "gen_speed_tps": round(tg_speed, 2),
        "total_elapsed_s": round(t_total, 2),
        "tokens_per_joule": round(eff_tokens_per_joule, 3)
    }
    print(f"[*] Result {name}: Pwr={res['avg_power_w']}W, Temp={res['avg_temp_c']}C (Max {res['max_temp_c']}C), Clock={res['avg_clock_mhz']}MHz, PP={res['prompt_speed_tps']} t/s, TG={res['gen_speed_tps']} t/s, Eff={res['tokens_per_joule']} tok/J")
    return res

def main():
    try:
        reset_gpu()
        
        # Test distinct key steps
        profiles = [
            ("Stock 250W", ["nvidia-smi -rgc", "nvidia-smi -pl 250"]),
            ("PowerLimit 200W", ["nvidia-smi -pl 200"]),
            ("PowerLimit 160W", ["nvidia-smi -pl 160"]),
            ("PowerLimit 130W", ["nvidia-smi -pl 130"]),
            ("PowerLimit 100W", ["nvidia-smi -pl 100"]),
            ("ClockLock 1260MHz", ["nvidia-smi -pl 250", "nvidia-smi -lgc 1260,1260"]),
            ("ClockLock 1110MHz", ["nvidia-smi -lgc 1110,1110"]),
            ("ClockLock 960MHz", ["nvidia-smi -lgc 960,960"]),
        ]
        
        results = []
        for name, cmds in profiles:
            res = test_llm_run(name, cmds, n_predict=250)
            if res:
                results.append(res)
            time.sleep(3)
            
        with open("/root/v100_llm_benchmark_results.json", "w") as f:
            json.dump(results, f, indent=2)
            
        print("\nAll LLM tests completed. Results saved to /root/v100_llm_benchmark_results.json")
    finally:
        reset_gpu()

if __name__ == "__main__":
    main()
