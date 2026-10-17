import os
import glob
import json
import math
import subprocess
import urllib.request
import collections

CHARS_PER_TOKEN = 4
BLOCK_OVERHEAD = 4

def estimate_dsh_tokens(message):
    tokens = 0
    content = message.get("content", [])
    for block in content:
        btype = block.get("type")
        if btype in ("text", "reasoning"):
            text = block.get("text", "")
            tokens += math.ceil(len(text) / CHARS_PER_TOKEN) + BLOCK_OVERHEAD
        elif btype == "tool-call":
            name = block.get("name", "")
            args = block.get("arguments", "")
            tokens += math.ceil(len(name) / CHARS_PER_TOKEN) + math.ceil(len(args) / CHARS_PER_TOKEN) + BLOCK_OVERHEAD
        else:
            tokens += BLOCK_OVERHEAD + math.ceil(len(json.dumps(block)) / CHARS_PER_TOKEN)
    return tokens + 4

def get_full_text(message):
    parts = []
    content = message.get("content", [])
    for block in content:
        btype = block.get("type")
        if btype == "reasoning":
            parts.append(f"<think>\n{block.get('text', '')}\n</think>")
        elif btype == "text":
            parts.append(block.get("text", ""))
        elif btype == "tool-call":
            parts.append(f"<tool_call>\n{block.get('name', '')}({block.get('arguments', '')})\n</tool_call>")
    return "\n".join(parts)

def tokenize_bpe_batch(texts, server_url="http://127.0.0.1:8081/tokenize"):
    results = []
    for text in texts:
        if not text:
            results.append(0)
            continue
        try:
            req = urllib.request.Request(
                server_url,
                data=json.dumps({"content": text}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                tokens = data.get("tokens", [])
                results.append(len(tokens))
        except Exception as e:
            # Fallback to estimate if llama-server fails
            results.append(math.ceil(len(text) / 3.0))
    return results

def main():
    session_files = sorted(glob.glob("/var/lib/docker/volumes/deepseek_dsh_home/_data/sessions/*/*/session.v4.jsonl.zstd"))
    print(f"Total session files found: {len(session_files)}")

    responses = []
    sessions_analyzed = 0

    for sf in session_files:
        proc = subprocess.Popen(["zstd", "-d", "-c", sf], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, _ = proc.communicate()
        lines = stdout.decode("utf-8", errors="replace").splitlines()
        has_assistant = False

        for line in lines:
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
                if ev.get("type") == "assistant/message":
                    msg = ev.get("data", {}).get("message", {})
                    if msg.get("role") == "assistant":
                        has_assistant = True
                        dsh_tokens = estimate_dsh_tokens(msg)
                        full_text = get_full_text(msg)
                        
                        # Breakdown
                        r_len = sum(len(b.get("text", "")) for b in msg.get("content", []) if b.get("type") == "reasoning")
                        t_len = sum(len(b.get("text", "")) for b in msg.get("content", []) if b.get("type") == "text")
                        tc_len = sum(len(b.get("name", "")) + len(b.get("arguments", "")) for b in msg.get("content", []) if b.get("type") == "tool-call")

                        responses.append({
                            "session": os.path.basename(os.path.dirname(sf)),
                            "seq": ev.get("seq"),
                            "turn": ev.get("data", {}).get("turn"),
                            "step": ev.get("data", {}).get("step"),
                            "dsh_tokens": dsh_tokens,
                            "full_text": full_text,
                            "chars_total": len(full_text),
                            "chars_reasoning": r_len,
                            "chars_text": t_len,
                            "chars_tool_call": tc_len
                        })
            except Exception:
                pass
        if has_assistant:
            sessions_analyzed += 1

    print(f"Analyzed {sessions_analyzed} active sessions with total {len(responses)} assistant responses.")
    if not responses:
        print("No assistant responses found!")
        return

    # Now calculate exact BPE tokens via /tokenize
    print("Tokenizing responses via llama-server /tokenize...")
    texts_to_tokenize = [r["full_text"] for r in responses]
    bpe_tokens = tokenize_bpe_batch(texts_to_tokenize)
    for r, bpe in zip(responses, bpe_tokens):
        r["bpe_tokens"] = bpe

    # Statistics calculation
    bpe_list = sorted([r["bpe_tokens"] for r in responses])
    dsh_list = sorted([r["dsh_tokens"] for r in responses])
    n = len(bpe_list)

    mean_bpe = sum(bpe_list) / n
    mean_dsh = sum(dsh_list) / n

    median_bpe = bpe_list[n // 2] if n % 2 != 0 else (bpe_list[n // 2 - 1] + bpe_list[n // 2]) / 2
    median_dsh = dsh_list[n // 2] if n % 2 != 0 else (dsh_list[n // 2 - 1] + dsh_list[n // 2]) / 2

    # Mode calculation using bins (e.g. 100-token bins and 250-token bins)
    def find_modal_bin(values, bin_size):
        bins = collections.Counter()
        for v in values:
            b_start = (v // bin_size) * bin_size
            b_end = b_start + bin_size - 1
            bins[(b_start, b_end)] += 1
        most_common = bins.most_common(5)
        return most_common

    modal_bins_100 = find_modal_bin(bpe_list, 100)
    modal_bins_250 = find_modal_bin(bpe_list, 250)
    modal_bins_500 = find_modal_bin(bpe_list, 500)

    # Exact value mode
    exact_counter = collections.Counter(bpe_list)
    top_exact = exact_counter.most_common(5)

    def percentile(values, p):
        k = (len(values) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return values[int(k)]
        d0 = values[int(f)] * (c - k)
        d1 = values[int(c)] * (k - f)
        return d0 + d1

    percentiles = {
        "P10": percentile(bpe_list, 0.10),
        "P25": percentile(bpe_list, 0.25),
        "P50": percentile(bpe_list, 0.50),
        "P75": percentile(bpe_list, 0.75),
        "P90": percentile(bpe_list, 0.90),
        "P95": percentile(bpe_list, 0.95),
        "P99": percentile(bpe_list, 0.99),
        "Max": bpe_list[-1],
        "Min": bpe_list[0]
    }

    # Bracket breakdown
    brackets = [
        ("0 - 250 токенов (короткие команды/тулзы)", sum(1 for v in bpe_list if v <= 250)),
        ("251 - 500 токенов (простые шаги)", sum(1 for v in bpe_list if 250 < v <= 500)),
        ("501 - 1000 токенов (средние ответы/рассуждения)", sum(1 for v in bpe_list if 500 < v <= 1000)),
        ("1001 - 2048 токенов (развернутые шаги с кодом)", sum(1 for v in bpe_list if 1000 < v <= 2048)),
        ("2049 - 4096 токенов (длинные рассуждения/скрипты)", sum(1 for v in bpe_list if 2048 < v <= 4096)),
        ("4097 - 8192 токенов (очень крупные генерации)", sum(1 for v in bpe_list if 4096 < v <= 8192)),
        ("> 8192 токенов (экстремальные генерации)", sum(1 for v in bpe_list if v > 8192)),
    ]

    # Components breakdown
    total_reasoning_chars = sum(r["chars_reasoning"] for r in responses)
    total_text_chars = sum(r["chars_text"] for r in responses)
    total_tool_chars = sum(r["chars_tool_call"] for r in responses)
    total_chars = sum(r["chars_total"] for r in responses)

    # Top 5 longest responses
    longest = sorted(responses, key=lambda x: x["bpe_tokens"], reverse=True)[:5]

    output = {
        "total_active_sessions": sessions_analyzed,
        "total_assistant_responses": n,
        "mean_bpe_tokens": round(mean_bpe, 2),
        "median_bpe_tokens": round(median_bpe, 2),
        "mean_dsh_meter_tokens": round(mean_dsh, 2),
        "percentiles_bpe": percentiles,
        "modal_bins_100": modal_bins_100,
        "modal_bins_250": modal_bins_250,
        "modal_bins_500": modal_bins_500,
        "top_exact_tokens": top_exact,
        "brackets": [
            {"bracket": b[0], "count": b[1], "pct": round(b[1] / n * 100, 2)} for b in brackets
        ],
        "components_pct": {
            "reasoning": round(total_reasoning_chars / max(1, total_chars) * 100, 2),
            "tool_calls": round(total_tool_chars / max(1, total_chars) * 100, 2),
            "text": round(total_text_chars / max(1, total_chars) * 100, 2)
        },
        "longest_responses": [
            {
                "session": l["session"],
                "seq": l["seq"],
                "turn": l["turn"],
                "step": l["step"],
                "bpe_tokens": l["bpe_tokens"],
                "dsh_tokens": l["dsh_tokens"],
                "snippet": l["full_text"][:200]
            } for l in longest
        ]
    }

    with open("/root/deepseek-harness/scratch/session_stats.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("        РЕЗУЛЬТАТЫ АНАЛИЗА СЕССИЙ DEEPSEEK HARNESS")
    print("=" * 60)
    print(f"Всего проанализировано сессий:      {sessions_analyzed}")
    print(f"Всего шагов ответов модели:         {n}")
    print(f"СРЕДНИЙ размер ответа (Mean):       {mean_bpe:.1f} токенов (BPE) | {mean_dsh:.1f} токенов (DSH Meter)")
    print(f"МЕДИАННЫЙ размер ответа (Median):   {median_bpe:.1f} токенов (BPE)")
    print(f"\nМОДАЛЬНЫЙ ДИАПАЗОН (наиболее частый размер):")
    for (start, end), count in modal_bins_250[:3]:
        print(f"  * {start:5d} - {end:5d} токенов: {count} ответов ({count / n * 100:.1f}%)")
    print(f"\nМодальные корзины по 100 токенов:")
    for (start, end), count in modal_bins_100[:3]:
        print(f"  * {start:5d} - {end:5d} токенов: {count} ответов ({count / n * 100:.1f}%)")
    
    print("\nПЕРЦЕНТИЛИ РАСПРЕДЕЛЕНИЯ ДЛИНЫ ОТВЕТА (BPE):")
    print(f"  P10:  {percentiles['P10']:.0f} токенов")
    print(f"  P25:  {percentiles['P25']:.0f} токенов")
    print(f"  P50:  {percentiles['P50']:.0f} токенов (половина ответов меньше этого)")
    print(f"  P75:  {percentiles['P75']:.0f} токенов")
    print(f"  P90:  {percentiles['P90']:.0f} токенов (90% ответов укладываются сюда)")
    print(f"  P95:  {percentiles['P95']:.0f} токенов (95% ответов укладываются сюда)")
    print(f"  P99:  {percentiles['P99']:.0f} токенов")
    print(f"  Max:  {percentiles['Max']:.0f} токенов")

    print("\nРАСПРЕДЕЛЕНИЕ ПО ДИАПАЗОНАМ:")
    for b in output["brackets"]:
        bar = "#" * int(b["pct"] / 2)
        print(f"  {b['bracket']:<50} | {b['count']:4d} ({b['pct']:5.1f}%) | {bar}")

    print("\nСТРУКТУРА ОБЪЕМА ГЕНЕРАЦИИ:")
    print(f"  Рассуждения (<think>): {output['components_pct']['reasoning']}%")
    print(f"  Вызовы тулзов:         {output['components_pct']['tool_calls']}%")
    print(f"  Финальный текст:       {output['components_pct']['text']}%")

    print("\nТОП-3 САМЫХ ДЛИННЫХ ОТВЕТА:")
    for i, l in enumerate(longest[:3], 1):
        print(f"  {i}. {l['bpe_tokens']} токенов (сессия {l['session']}, turn {l['turn']}, step {l['step']})")

if __name__ == "__main__":
    main()
