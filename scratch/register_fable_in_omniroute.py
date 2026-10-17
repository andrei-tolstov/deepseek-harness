import sqlite3
import json
import os
import datetime

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"

# 1. Backup first
now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak_path = f"/root/backup_storage_fable_{now_str}.sqlite"
os.system(f"cp {db_path} {bak_path}")
print(f"Backed up sqlite to {bak_path}")

conn = sqlite3.connect(db_path)
c = conn.cursor()

# 2. Add or update provider_nodes
node_id = "openai-compatible-chat-fable-v100"
node_name = "Fable Cold Fusion Tesla V100"
prefix = "fable"
api_type = "chat"
base_url = "http://192.168.50.101:8083/v1"
chat_path = "/chat/completions"
models_path = "/models"
now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

c.execute("DELETE FROM provider_nodes WHERE id = ?", (node_id,))
c.execute("""
    INSERT INTO provider_nodes (id, type, name, prefix, api_type, base_url, chat_path, models_path, custom_headers_json, created_at, updated_at)
    VALUES (?, 'openai-compatible', ?, ?, ?, ?, ?, ?, NULL, ?, ?)
""", (node_id, node_name, prefix, api_type, base_url, chat_path, models_path, now_iso, now_iso))
print("Inserted provider_node:", node_id)

# 3. Add or update provider_connections
conn_id = "conn-fable"
conn_name = "fable-conn"
provider_specific_data = json.dumps({
    "baseUrl": base_url,
    "autoSync": False,
    "autoFetchModels": False
})
enc_api_key = "enc:v1:1bb34eec10bb91677c1c2470fb6fdb03:3f69543f:f6c8e2e3c24d60875b74ed1916eea551"

c.execute("DELETE FROM provider_connections WHERE id = ?", (conn_id,))
c.execute("""
    INSERT INTO provider_connections (
        id, provider, auth_type, name, priority, is_active, test_status,
        api_key, provider_specific_data, proxy_enabled, per_key_proxy_enabled,
        quota_visible, created_at, updated_at, synced_models_at
    ) VALUES (
        ?, ?, 'apikey', ?, 1, 1, 'active',
        ?, ?, 1, 0,
        1, ?, ?, ?
    )
""", (conn_id, node_id, conn_name, enc_api_key, provider_specific_data, now_iso, now_iso, now_iso))
print("Inserted provider_connection:", conn_id)

# 4. Add models to key_value
fable_models = [
    {
        "id": "fable-cold-fusion-27b",
        "name": "Fable Cold Fusion 27B",
        "source": "imported",
        "inputTokenLimit": 205000,
        "contextWindow": 205000,
        "supportsVision": True,
        "capabilities": {
            "vision": True,
            "tool_calling": True,
            "reasoning": True
        },
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"]
    },
    {
        "id": "fable",
        "name": "Fable Cold Fusion",
        "source": "imported",
        "inputTokenLimit": 205000,
        "contextWindow": 205000,
        "supportsVision": True,
        "capabilities": {
            "vision": True,
            "tool_calling": True,
            "reasoning": True
        },
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"]
    },
    {
        "id": "qwen3.8-fable",
        "name": "Qwen 3.8 Fable",
        "source": "imported",
        "inputTokenLimit": 205000,
        "contextWindow": 205000,
        "supportsVision": True,
        "capabilities": {
            "vision": True,
            "tool_calling": True,
            "reasoning": True
        },
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"]
    },
    {
        "id": "default",
        "name": "Fable Default",
        "source": "imported",
        "inputTokenLimit": 205000,
        "contextWindow": 205000,
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
c.execute("DELETE FROM key_value WHERE namespace = ? AND key = ?", (namespace, kv_key))
c.execute("INSERT INTO key_value (namespace, key, value) VALUES (?, ?, ?)", (namespace, kv_key, json.dumps(fable_models, ensure_ascii=False)))
print("Inserted key_value with namespace syncedAvailableModels:", kv_key)

# 5. Add model_context_overrides
target_providers = [node_id, prefix, conn_name]
target_model_ids = ["fable-cold-fusion-27b", "fable", "qwen3.8-fable", "default"]

for p in target_providers:
    for m in target_model_ids:
        c.execute("DELETE FROM model_context_overrides WHERE provider = ? AND model_id = ?", (p, m))
        c.execute("""
            INSERT INTO model_context_overrides (provider, model_id, real_context, source, refreshed_at)
            VALUES (?, ?, 205000, 'manual', datetime('now'))
        """, (p, m))
        print(f"Added model_context_overrides: {p} / {m} -> 205000")

conn.commit()
conn.close()

os.system(f"chown 1000:1000 {db_path}")
print("OmniRoute DB successfully updated and permissions set to 1000:1000")
