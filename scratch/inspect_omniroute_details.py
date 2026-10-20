import sqlite3
import json

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== PROVIDER NODES ===")
for r in c.execute("SELECT id, name, prefix, base_url FROM provider_nodes").fetchall():
    print(r)

print("\n=== PROVIDER CONNECTIONS ===")
for r in c.execute("SELECT id, provider, name, is_active FROM provider_connections").fetchall():
    print(r)

print("\n=== SYNCED AVAILABLE MODELS ===")
for r in c.execute("SELECT key, value FROM key_value WHERE namespace='syncedAvailableModels'").fetchall():
    try:
        val = json.loads(r[1])
        print(r[0], ":", [m.get("id") for m in val])
    except Exception as e:
        print(r[0], ":", e)

print("\n=== MODEL CONTEXT OVERRIDES ===")
for r in c.execute("SELECT provider, model_id, real_context FROM model_context_overrides").fetchall():
    print(r)

print("\n=== API KEYS ===")
for r in c.execute("SELECT id, name, allowed_models FROM api_keys").fetchall():
    try:
        models = json.loads(r[2] or "[]")
    except Exception:
        models = r[2]
    print(r[0], r[1], models)

conn.close()
