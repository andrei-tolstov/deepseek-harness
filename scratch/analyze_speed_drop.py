import os
import re
import json
import sqlite3
import glob

# 1. Parse llama-server logs for exact token generation speeds
log_path = "/var/lib/docker/containers/7bc51001b20d09515d5b0ce9b969cab107cdac9b0ecfa1f623cd0530e423a0b6/7bc51001b20d09515d5b0ce9b969cab107cdac9b0ecfa1f623cd0530e423a0b6-json.log"

llama_tasks = {}

with open(log_path, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        try:
            entry = json.loads(line)
            log_line = entry.get("log", "")
            time_str = entry.get("time", "")

            m_prompt = re.search(r"task\s+(\d+)\s+\|\s+prompt eval time =\s+([\d\.]+)\s+ms\s+/\s+(\d+)\s+tokens\s+\(\s*([\d\.]+)\s+ms per token,\s+([\d\.]+)\s+tokens per second\)", log_line)
            if m_prompt:
                tid = int(m_prompt.group(1))
                if tid not in llama_tasks: llama_tasks[tid] = {"task_id": tid, "time": time_str}
                llama_tasks[tid]["prompt_eval_ms"] = float(m_prompt.group(2))
                llama_tasks[tid]["prompt_tokens"] = int(m_prompt.group(3))
                llama_tasks[tid]["prompt_ms_per_tok"] = float(m_prompt.group(4))
                llama_tasks[tid]["prompt_tps"] = float(m_prompt.group(5))

            m_eval = re.search(r"task\s+(\d+)\s+\|\s+eval time =\s+([\d\.]+)\s+ms\s+/\s+(\d+)\s+tokens\s+\(\s*([\d\.]+)\s+ms per token,\s+([\d\.]+)\s+tokens per second\)", log_line)
            if m_eval:
                tid = int(m_eval.group(1))
                if tid not in llama_tasks: llama_tasks[tid] = {"task_id": tid, "time": time_str}
                llama_tasks[tid]["eval_ms"] = float(m_eval.group(2))
                llama_tasks[tid]["eval_tokens"] = int(m_eval.group(3))
                llama_tasks[tid]["eval_ms_per_tok"] = float(m_eval.group(4))
                llama_tasks[tid]["eval_tps"] = float(m_eval.group(5))

            m_draft = re.search(r"task\s+(\d+)\s+\|\s+draft acceptance =\s+([\d\.]+)\s+\(\s*(\d+)\s+accepted\s+/\s+(\d+)\s+generated\)", log_line)
            if m_draft:
                tid = int(m_draft.group(1))
                if tid in llama_tasks:
                    llama_tasks[tid]["draft_acceptance"] = float(m_draft.group(2))
        except Exception:
            pass

valid_llama = [t for t in llama_tasks.values() if "eval_tps" in t and "prompt_tokens" in t and t["eval_tokens"] > 5]
print(f"Loaded {len(valid_llama)} generation measurements from llama-server.")

# 2. Correlate with OmniRoute call_logs to get DSH sessions
conn = sqlite3.connect("/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite")
cursor = conn.cursor()
cursor.execute("SELECT id, timestamp, model, duration, tokens_in, tokens_out, session_tag FROM call_logs WHERE status=200")
call_logs = cursor.fetchall()

# 3. Read session metadata from DSH
session_titles = {}
for sf in glob.glob("/var/lib/docker/volumes/deepseek_dsh_home/_data/sessions/*/*/session.v4.jsonl.zstd"):
    s_id = os.path.basename(os.path.dirname(sf))
    workspace = sf.split("/")[-3]
    session_titles[s_id] = {"workspace": workspace, "id": s_id}

print(f"Found {len(session_titles)} DSH session folders.")

# Match llama tasks with call_logs by tokens_in & tokens_out
for lt in valid_llama:
    matched = None
    for cl in call_logs:
        cl_id, cl_ts, cl_model, cl_dur, cl_tin, cl_tout, cl_stag = cl
        if cl_tin == lt["prompt_tokens"] and cl_tout == lt["eval_tokens"]:
            matched = cl
            break
    if matched:
        lt["session_tag"] = matched[6]
        lt["model"] = matched[2]
        clean_sid = (matched[6] or "").replace("conv_", "")
        if clean_sid in session_titles:
            lt["workspace"] = session_titles[clean_sid]["workspace"]

# Binning
bins = [
    ("0 - 2K", 0, 2000),
    ("14K - 20K", 14000, 20000),
    ("20K - 25K", 20000, 25000),
    ("25K - 30K", 25000, 30000),
    ("30K - 40K", 30000, 40000),
    ("60K - 70K", 60000, 70000),
    ("90K - 100K", 90000, 100000)
]

binned_results = []
baseline_tps = None

for label, low, high in bins:
    items = [x for x in valid_llama if low <= x["prompt_tokens"] < high]
    if not items:
        continue
    cnt = len(items)
    avg_prompt_tokens = sum(x["prompt_tokens"] for x in items) / cnt
    avg_eval_tokens = sum(x["eval_tokens"] for x in items) / cnt
    avg_eval_tps = sum(x["eval_tps"] for x in items) / cnt
    med_eval_tps = sorted([x["eval_tps"] for x in items])[cnt // 2]
    avg_eval_ms_per_tok = sum(x["eval_ms_per_tok"] for x in items) / cnt
    
    avg_prompt_tps = sum(x.get("prompt_tps", 0) for x in items) / cnt
    avg_ttft_sec = (sum(x.get("prompt_eval_ms", 0) for x in items) / cnt) / 1000.0
    
    drafts = [x["draft_acceptance"] for x in items if "draft_acceptance" in x]
    avg_draft = (sum(drafts) / len(drafts)) if drafts else 0.0

    if baseline_tps is None and label == "14K - 20K":
        baseline_tps = avg_eval_tps

    drop_pct = 0.0
    if baseline_tps:
        drop_pct = ((baseline_tps - avg_eval_tps) / baseline_tps) * 100.0

    binned_results.append({
        "bin": label,
        "count": cnt,
        "avg_context": avg_prompt_tokens,
        "avg_eval_tokens": avg_eval_tokens,
        "avg_eval_tps": avg_eval_tps,
        "med_eval_tps": med_eval_tps,
        "avg_eval_ms_per_tok": avg_eval_ms_per_tok,
        "avg_prompt_tps": avg_prompt_tps,
        "avg_ttft_sec": avg_ttft_sec,
        "avg_draft": avg_draft,
        "drop_pct": drop_pct
    })

print("\n" + "="*110)
print(f"{'Контекст (токенов)':<18} | {'Выборка':<8} | {'Скорость ген. (t/s)':<20} | {'Задержка (мс/ток)':<18} | {'TTFT (сек)':<12} | {'Draft MTP %':<12} | {'Падение скорости':<16}")
print("="*110)
for r in binned_results:
    tps_str = f"{r['avg_eval_tps']:.1f} (мед: {r['med_eval_tps']:.1f})"
    drop_str = f"-{r['drop_pct']:.1f}%" if r['drop_pct'] > 0 else "0.0% (база)"
    draft_str = f"{r['avg_draft']*100:.1f}%" if r['avg_draft'] > 0 else "N/A"
    print(f"{r['bin']:<18} | {r['count']:<8} | {tps_str:<20} | {r['avg_eval_ms_per_tok']:<18.2f} | {r['avg_ttft_sec']:<12.1f} | {draft_str:<12} | {drop_str:<16}")
print("="*110)

# Save json output
with open("/tmp/speed_analysis_results.json", "w", encoding="utf-8") as f:
    json.dump({
        "binned_results": binned_results,
        "raw_tasks": valid_llama
    }, f, indent=2, ensure_ascii=False)
