import sqlite3
import json
import os

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

node_id = "openai-compatible-chat-fable-v100"
conn_id = "conn-fable"
prefix = "fable"

# 1. Update syncedAvailableModels in key_value with ONLY ONE model
single_model = [
    {
        "id": "fable-cold-fusion-27b",
        "name": "Fable Cold Fusion 27B",
        "source": "imported",
        "inputTokenLimit": 190000,
        "contextWindow": 190000,
        "supportsVision": True,
        "capabilities": {
            "vision": True,
            "tool_calling": True,
            "reasoning": True
        },
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"]
    }
]

kv_key = f"{node_id}:{conn_id}"
namespace = "syncedAvailableModels"
c.execute("UPDATE key_value SET value = ? WHERE namespace = ? AND key = ?", (json.dumps(single_model, ensure_ascii=False), namespace, kv_key))
print(f"Updated {namespace} {kv_key} with single model: fable-cold-fusion-27b (190000 tokens)")

# 2. Clean up model_context_overrides
c.execute("DELETE FROM model_context_overrides WHERE provider IN (?, ?, 'fable-conn') AND model_id != 'fable-cold-fusion-27b'", (node_id, prefix))
print(f"Cleaned up model_context_overrides, deleted non-fable-cold-fusion-27b entries: {c.rowcount}")

# Ensure the single model override exists
for p in [node_id, prefix, 'fable-conn']:
    c.execute("DELETE FROM model_context_overrides WHERE provider = ? AND model_id = 'fable-cold-fusion-27b'", (p,))
    c.execute("""
        INSERT INTO model_context_overrides (provider, model_id, real_context, source, refreshed_at)
        VALUES (?, 'fable-cold-fusion-27b', 190000, 'manual', datetime('now'))
    """, (p,))
    print(f"Ensured model_context_overrides for {p} / fable-cold-fusion-27b -> 190000")

# 3. Clean up api_keys allowed_models
dsh_key_id = "b3f368c2-9fb3-4019-859c-3780f21a25c5"
r = c.execute("SELECT allowed_models, allowed_connections FROM api_keys WHERE id = ?", (dsh_key_id,)).fetchone()
if r:
    models = json.loads(r[0] or "[]")
    conns = json.loads(r[1] or "[]")
    
    # Remove any unwanted fable aliases
    unwanted = ["fable", "qwen3.8-fable", "fable/fable", "fable/qwen3.8-fable", "fable/default", "fable/*"]
    models = [m for m in models if m not in unwanted]
    
    # Keep only the single official model ID
    if "fable/fable-cold-fusion-27b" not in models:
        models.append("fable/fable-cold-fusion-27b")
    if "conn-fable" not in conns:
        conns.append("conn-fable")
        
    c.execute("""
        UPDATE api_keys
        SET allowed_models = ?, allowed_connections = ?
        WHERE id = ?
    """, (json.dumps(models), json.dumps(conns), dsh_key_id))
    print(f"Updated allowed_models for {dsh_key_id} to only include fable/fable-cold-fusion-27b")

conn.commit()
conn.close()

os.system(f"chown 1000:1000 {db_path}")
print("Successfully set single fable alias in OmniRoute")
