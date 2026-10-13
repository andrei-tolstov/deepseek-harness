import sqlite3
import json
import os
import datetime

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"

# Backup first
now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak_path = f"/root/backup_storage_{now_str}.sqlite"
os.system(f"cp {db_path} {bak_path}")
print(f"Backed up sqlite to {bak_path}")

conn = sqlite3.connect(db_path)
c = conn.cursor()

# 1. Update model_context_overrides
target_models = ['default', 'qwen3.8', 'qwen3.8-27b']
target_providers = ['openai-compatible-chat-qwen38-v100', 'qwen38']

for p in target_providers:
    for m in target_models:
        c.execute("""
            UPDATE model_context_overrides
            SET real_context = 180000, source = 'manual', refreshed_at = datetime('now')
            WHERE provider = ? AND model_id = ?
        """, (p, m))
        print(f"Updated model_context_overrides for {p} / {m}: {c.rowcount} rows")

# 2. Update key_value table for openai-compatible-chat-qwen38-v100:conn-qwen38
kv_key = 'openai-compatible-chat-qwen38-v100:conn-qwen38'
row = c.execute("SELECT value FROM key_value WHERE key = ?", (kv_key,)).fetchone()
if row:
    val = json.loads(row[0])
    for item in val:
        if item.get("id") in target_models:
            item["inputTokenLimit"] = 180000
            item["contextWindow"] = 180000
            print(f"Updated JSON item {item.get('id')} to 180000")
    new_json_str = json.dumps(val, ensure_ascii=False)
    c.execute("UPDATE key_value SET value = ? WHERE key = ?", (new_json_str, kv_key))
    print("Updated key_value table row count:", c.rowcount)

conn.commit()
conn.close()

# Ensure file ownership
os.system(f"chown 1000:1000 {db_path}")
print("OmniRoute DB updated successfully")
