import re
import json

log_path = "/var/lib/docker/containers/7bc51001b20d09515d5b0ce9b969cab107cdac9b0ecfa1f623cd0530e423a0b6/7bc51001b20d09515d5b0ce9b969cab107cdac9b0ecfa1f623cd0530e423a0b6-json.log"

tasks = {}

with open(log_path, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        try:
            entry = json.loads(line)
            log_line = entry.get("log", "")
            time_str = entry.get("time", "")
            
            # Match prompt eval: prompt eval time =   60625.52 ms / 35073 tokens (    1.73 ms per token,   578.52 tokens per second)
            m_prompt = re.search(r"task\s+(\d+)\s+\|\s+prompt eval time =\s+([\d\.]+)\s+ms\s+/\s+(\d+)\s+tokens\s+\(\s*([\d\.]+)\s+ms per token,\s+([\d\.]+)\s+tokens per second\)", log_line)
            if m_prompt:
                tid = int(m_prompt.group(1))
                if tid not in tasks: tasks[tid] = {"task_id": tid, "time": time_str}
                tasks[tid]["prompt_eval_ms"] = float(m_prompt.group(2))
                tasks[tid]["prompt_tokens"] = int(m_prompt.group(3))
                tasks[tid]["prompt_ms_per_token"] = float(m_prompt.group(4))
                tasks[tid]["prompt_tps"] = float(m_prompt.group(5))

            # Match eval time: eval time =   47032.05 ms /  1535 tokens (   30.66 ms per token,    32.62 tokens per second)
            m_eval = re.search(r"task\s+(\d+)\s+\|\s+eval time =\s+([\d\.]+)\s+ms\s+/\s+(\d+)\s+tokens\s+\(\s*([\d\.]+)\s+ms per token,\s+([\d\.]+)\s+tokens per second\)", log_line)
            if m_eval:
                tid = int(m_eval.group(1))
                if tid not in tasks: tasks[tid] = {"task_id": tid, "time": time_str}
                tasks[tid]["eval_ms"] = float(m_eval.group(2))
                tasks[tid]["eval_tokens"] = int(m_eval.group(3))
                tasks[tid]["eval_ms_per_token"] = float(m_eval.group(4))
                tasks[tid]["eval_tps"] = float(m_eval.group(5))

            # Match draft acceptance: draft acceptance = 0.42694 (  862 accepted /  2019 generated), mean len =  2.28
            m_draft = re.search(r"task\s+(\d+)\s+\|\s+draft acceptance =\s+([\d\.]+)\s+\(\s*(\d+)\s+accepted\s+/\s+(\d+)\s+generated\)", log_line)
            if m_draft:
                tid = int(m_draft.group(1))
                if tid in tasks:
                    tasks[tid]["draft_acceptance"] = float(m_draft.group(2))
                    tasks[tid]["draft_accepted"] = int(m_draft.group(3))
                    tasks[tid]["draft_generated"] = int(m_draft.group(4))

            # Match prompt processing progress (chunked prefill)
            # prompt processing, n_tokens =  27168, progress = 0.76, t =  42.66 s / 636.84 tokens per second
            m_chunk = re.search(r"task\s+(\d+)\s+\|\s+prompt processing,\s+n_tokens =\s+(\d+),\s+progress =\s+([\d\.]+),\s+t =\s+([\d\.]+)\s+s\s+/\s+([\d\.]+)\s+tokens per second", log_line)
            if m_chunk:
                tid = int(m_chunk.group(1))
                if tid not in tasks: tasks[tid] = {"task_id": tid, "time": time_str}
                if "chunks" not in tasks[tid]: tasks[tid]["chunks"] = []
                tasks[tid]["chunks"].append({
                    "n_tokens": int(m_chunk.group(2)),
                    "progress": float(m_chunk.group(3)),
                    "t_sec": float(m_chunk.group(4)),
                    "tps": float(m_chunk.group(5))
                })
        except Exception:
            pass

print(f"Total parsed tasks in qwen38: {len(tasks)}")
valid = [t for t in tasks.values() if "eval_tps" in t and "prompt_tokens" in t]
print(f"Tasks with complete eval timings: {len(valid)}")

# Sort by prompt_tokens
valid_sorted = sorted(valid, key=lambda x: x["prompt_tokens"])
print("\nSample records sorted by prompt_tokens (context length):")
print(f"{'Task':<6} | {'Context (tok)':<14} | {'Eval Toks':<10} | {'Gen (tok/s)':<12} | {'Prompt (tok/s)':<14} | {'Prompt ms':<10} | {'Draft Acc':<10}")
print("-" * 85)
for t in valid_sorted:
    draft = f"{t.get('draft_acceptance', 0):.2f}" if "draft_acceptance" in t else "N/A"
    print(f"{t['task_id']:<6} | {t['prompt_tokens']:<14} | {t['eval_tokens']:<10} | {t['eval_tps']:<12.2f} | {t.get('prompt_tps', 0):<14.2f} | {t.get('prompt_eval_ms', 0):<10.1f} | {draft:<10}")
