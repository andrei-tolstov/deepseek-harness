import sqlite3

conn = sqlite3.connect("/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite")
cursor = conn.cursor()

query = """
SELECT id, timestamp, model, duration, tokens_in, tokens_out, tokens_cache_read, tokens_cache_creation, session_tag
FROM call_logs
WHERE status = 200 AND model IN ('qwen3.8', 'qwen3.8-27b') AND tokens_out > 0 AND tokens_in > 0
ORDER BY tokens_in ASC
"""

cursor.execute(query)
rows = cursor.fetchall()
print(f"Total valid call_logs for qwen: {len(rows)}")

# Range analysis
# Bins of context: 0-5k, 5k-15k, 15k-30k, 30k-50k, 50k-70k, 70k-100k, 100k+
bins = [
    (0, 5000),
    (5000, 15000),
    (15000, 30000),
    (30000, 50000),
    (50000, 70000),
    (70000, 90000),
    (90000, 120000)
]

bin_stats = {b: [] for b in bins}

for r in rows:
    _id, ts, model, duration, tokens_in, tokens_out, c_read, c_create, s_tag = r
    total_sec = duration / 1000.0
    for b in bins:
        if b[0] <= tokens_in < b[1]:
            bin_stats[b].append({
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "duration_sec": total_sec,
                "tokens_cache_read": c_read or 0
            })
            break

print("\nCall logs summary by Context Size (tokens_in):")
print(f"{'Context Range':<18} | {'Count':<6} | {'Avg In':<8} | {'Avg Out':<8} | {'Avg Sec':<8} | {'Median Sec':<10} | {'Avg CacheRead':<14}")
print("-" * 85)

for b in bins:
    items = bin_stats[b]
    if not items:
        continue
    cnt = len(items)
    avg_in = sum(x["tokens_in"] for x in items) / cnt
    avg_out = sum(x["tokens_out"] for x in items) / cnt
    avg_sec = sum(x["duration_sec"] for x in items) / cnt
    durations = sorted([x["duration_sec"] for x in items])
    med_sec = durations[cnt // 2]
    avg_cread = sum(x["tokens_cache_read"] for x in items) / cnt
    range_str = f"{b[0]} - {b[1]}"
    print(f"{range_str:<18} | {cnt:<6} | {avg_in:<8.0f} | {avg_out:<8.0f} | {avg_sec:<8.1f} | {med_sec:<10.1f} | {avg_cread:<14.0f}")
