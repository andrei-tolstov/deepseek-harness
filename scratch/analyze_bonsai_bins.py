import json
import re

log_path = "/var/lib/docker/containers/ae1b5472a193827c6edb3784b0b9de70270edfa4858c44f4076376df74a8cf9b/ae1b5472a193827c6edb3784b0b9de70270edfa4858c44f4076376df74a8cf9b-json.log"
tasks = {}

with open(log_path, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        try:
            entry = json.loads(line)
            log_line = entry.get("log", "")
            time_str = entry.get("time", "")

            m_prompt = re.search(r"task\s+(\d+)\s+\|\s+prompt eval time =\s+([\d\.]+)\s+ms\s+/\s+(\d+)\s+tokens\s+\(\s*([\d\.]+)\s+ms per token,\s+([\d\.]+)\s+tokens per second\)", log_line)
            if m_prompt:
                tid = int(m_prompt.group(1))
                if tid not in tasks: tasks[tid] = {"task_id": tid, "time": time_str}
                tasks[tid]["prompt_eval_ms"] = float(m_prompt.group(2))
                tasks[tid]["prompt_tokens"] = int(m_prompt.group(3))
                tasks[tid]["prompt_tps"] = float(m_prompt.group(5))

            m_eval = re.search(r"task\s+(\d+)\s+\|\s+eval time =\s+([\d\.]+)\s+ms\s+/\s+(\d+)\s+tokens\s+\(\s*([\d\.]+)\s+ms per token,\s+([\d\.]+)\s+tokens per second\)", log_line)
            if m_eval:
                tid = int(m_eval.group(1))
                if tid not in tasks: tasks[tid] = {"task_id": tid, "time": time_str}
                tasks[tid]["eval_ms"] = float(m_eval.group(2))
                tasks[tid]["eval_tokens"] = int(m_eval.group(3))
                tasks[tid]["eval_ms_per_tok"] = float(m_eval.group(4))
                tasks[tid]["eval_tps"] = float(m_eval.group(5))
        except Exception:
            pass

valid = [t for t in tasks.values() if "eval_tps" in t and "prompt_tokens" in t and t["eval_tokens"] > 10]
print(f"Bonsai2 valid: {len(valid)}")
bins = [
    ("0 - 500", 0, 500),
    ("500 - 1K", 500, 1000),
    ("1K - 5K", 1000, 5000),
    ("5K - 15K", 5000, 15000),
    ("15K - 50K", 15000, 50000)
]
for label, low, high in bins:
    items = [x for x in valid if low <= x["prompt_tokens"] < high]
    if items:
        avg_tps = sum(x["eval_tps"] for x in items) / len(items)
        med_tps = sorted([x["eval_tps"] for x in items])[len(items)//2]
        avg_ptps = sum(x.get("prompt_tps", 0) for x in items) / len(items)
        print(f"Bonsai2 {label:<10} (n={len(items):<3}): gen={avg_tps:.1f} t/s (med {med_tps:.1f}), prompt={avg_ptps:.1f} t/s")
