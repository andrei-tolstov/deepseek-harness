import sqlite3
import json
import os
import datetime

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"

# 1. Backup first
now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak_path = f"/root/backup_storage_coder390_{now_str}.sqlite"
os.system(f"cp {db_path} {bak_path}")
print(f"Backed up sqlite to {bak_path}")

conn = sqlite3.connect(db_path)
c = conn.cursor()

# 2. Add or update provider_nodes
node_id = "openai-compatible-chat-coder390-v100"
node_name = "Qwen 3.8 Coder390 Tesla V100"
prefix = "coder390"
api_type = "chat"
base_url = "http://192.168.50.38:8084/v1"
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
conn_id = "conn-coder390"
conn_name = "coder390-conn"
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

# 4. Add EXACTLY ONE model to syncedAvailableModels in key_value (no aliases)
single_model_id = "coder390-27b"
coder390_models = [
    {
        "id": single_model_id,
        "name": "Qwen 3.8 Coder390 27B",
        "source": "imported",
        "inputTokenLimit": 180000,
        "contextWindow": 180000,
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
c.execute("""
    INSERT INTO key_value (namespace, key, value)
    VALUES (?, ?, ?)
""", (namespace, kv_key, json.dumps(coder390_models, ensure_ascii=False)))
print(f"Set {namespace} for {kv_key} to exactly 1 model: {single_model_id}")

# 5. Model context overrides (protect 180K window from reset)
for p in [node_id, prefix, conn_id]:
    c.execute("DELETE FROM model_context_overrides WHERE provider = ? AND model_id = ?", (p, single_model_id))
    c.execute("""
        INSERT INTO model_context_overrides (provider, model_id, real_context, source, refreshed_at)
        VALUES (?, ?, 180000, 'manual', datetime('now'))
    """, (p, single_model_id))
    print(f"Ensured model_context_overrides for {p} / {single_model_id} -> 180000")

# 6. Update api_keys allowed_models and allowed_connections
dsh_key_id = "b3f368c2-9fb3-4019-859c-3780f21a25c5"
r = c.execute("SELECT allowed_models, allowed_connections FROM api_keys WHERE id = ?", (dsh_key_id,)).fetchone()
if r:
    models = json.loads(r[0] or "[]")
    conns = json.loads(r[1] or "[]")

    # Remove any stray coder390 variants if any existed
    unwanted = ["coder390", "qwen3.8-coder390", "coder390/*", "coder390/default"]
    models = [m for m in models if m not in unwanted]

    # Exactly one record for coder390
    model_canonical = f"{prefix}/{single_model_id}"
    if model_canonical not in models:
        models.append(model_canonical)
    if conn_id not in conns:
        conns.append(conn_id)

    c.execute("""
        UPDATE api_keys
        SET allowed_models = ?, allowed_connections = ?
        WHERE id = ?
    """, (json.dumps(models), json.dumps(conns), dsh_key_id))
    print(f"Updated allowed_models for {dsh_key_id} with single entry: {model_canonical}")

conn.commit()
conn.close()

# Ensure OmniRoute container permissions
os.system(f"chown 1000:1000 {db_path}")
print("Successfully registered Coder390 in OmniRoute DB!")
