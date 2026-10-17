import re
import json

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
                tasks[tid]["prompt_ms_per_token"] = float(m_prompt.group(4))
                tasks[tid]["prompt_tps"] = float(m_prompt.group(5))

            m_eval = re.search(r"task\s+(\d+)\s+\|\s+eval time =\s+([\d\.]+)\s+ms\s+/\s+(\d+)\s+tokens\s+\(\s*([\d\.]+)\s+ms per token,\s+([\d\.]+)\s+tokens per second\)", log_line)
            if m_eval:
                tid = int(m_eval.group(1))
                if tid not in tasks: tasks[tid] = {"task_id": tid, "time": time_str}
                tasks[tid]["eval_ms"] = float(m_eval.group(2))
                tasks[tid]["eval_tokens"] = int(m_eval.group(3))
                tasks[tid]["eval_ms_per_token"] = float(m_eval.group(4))
                tasks[tid]["eval_tps"] = float(m_eval.group(5))

            m_draft = re.search(r"task\s+(\d+)\s+\|\s+draft acceptance =\s+([\d\.]+)\s+\(\s*(\d+)\s+accepted\s+/\s+(\d+)\s+generated\)", log_line)
            if m_draft:
                tid = int(m_draft.group(1))
                if tid in tasks:
                    tasks[tid]["draft_acceptance"] = float(m_draft.group(2))
        except Exception:
            pass

valid = [t for t in tasks.values() if "eval_tps" in t and "prompt_tokens" in t]
print(f"Total tasks in bonsai2: {len(tasks)}, valid: {len(valid)}")
valid_sorted = sorted(valid, key=lambda x: x["prompt_tokens"])
print(f"{'Task':<6} | {'Context (tok)':<14} | {'Eval Toks':<10} | {'Gen (tok/s)':<12} | {'Prompt (tok/s)':<14} | {'Prompt ms':<10} | {'Draft Acc':<10}")
print("-" * 85)
for t in valid_sorted[::max(1, len(valid_sorted)//20)]: # sample ~20
    draft = f"{t.get('draft_acceptance', 0):.2f}" if "draft_acceptance" in t else "N/A"
    print(f"{t['task_id']:<6} | {t['prompt_tokens']:<14} | {t['eval_tokens']:<10} | {t['eval_tps']:<12.2f} | {t.get('prompt_tps', 0):<14.2f} | {t.get('prompt_eval_ms', 0):<10.1f} | {draft:<10}")
