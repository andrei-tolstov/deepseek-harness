import sqlite3
import json

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

# 1. Inspect api_keys columns
cols = [col[1] for col in c.execute("PRAGMA table_info(api_keys)").fetchall()]
print("Columns in api_keys:", cols)

# 2. Update allowed_models and allowed_combos for all keys that need it
combo_name = "andrei-router"
combo_id = "0714a926-7391-402c-9b6e-5b894c38d865"

for r in c.execute("SELECT id, name, allowed_models FROM api_keys").fetchall():
    key_id, name, allowed_models_raw = r
    try:
        models = json.loads(allowed_models_raw or "[]")
    except Exception:
        models = []

    if combo_name not in models:
        models.append(combo_name)
    if combo_id not in models:
        models.append(combo_id)

    c.execute("UPDATE api_keys SET allowed_models = ? WHERE id = ?", (json.dumps(models), key_id))
    print(f"Updated api_key {name} ({key_id}) with allowed_models including {combo_name}")

if "allowed_combos" in cols:
    for r in c.execute("SELECT id, name, allowed_combos FROM api_keys").fetchall():
        key_id, name, allowed_combos_raw = r
        try:
            combos = json.loads(allowed_combos_raw or "[]")
        except Exception:
            combos = []
        if combo_id not in combos:
            combos.append(combo_id)
        if combo_name not in combos:
            combos.append(combo_name)
        c.execute("UPDATE api_keys SET allowed_combos = ? WHERE id = ?", (json.dumps(combos), key_id))
        print(f"Updated allowed_combos for {name}")

# Also ensure model_combo_mappings has a pattern entry
c.execute("DELETE FROM model_combo_mappings WHERE combo_id = ? OR pattern = ?", (combo_id, combo_name))
c.execute("""
    INSERT INTO model_combo_mappings (id, pattern, combo_id, priority, enabled, description, created_at, updated_at)
    VALUES (?, ?, ?, 100, 1, 'Auto route to active model on Tesla V100', datetime('now'), datetime('now'))
""", (f"mcm-{combo_name}", combo_name, combo_id))
print("Added model_combo_mappings for", combo_name)

# Also ensure model_context_overrides for andrei-router -> 180000
for p in ["combos", "router", "omniroute", "andrei-router"]:
    c.execute("DELETE FROM model_context_overrides WHERE provider = ? AND model_id = ?", (p, combo_name))
    c.execute("""
        INSERT INTO model_context_overrides (provider, model_id, real_context, source, refreshed_at)
        VALUES (?, ?, 180000, 'manual', datetime('now'))
    """, (p, combo_name))
print("Configured context override for andrei-router -> 180000")

# Set catalog_scope to 'all' so combos appear in /v1/models alongside models
c.execute("UPDATE api_keys SET catalog_scope = 'all' WHERE id = 'b3f368c2-9fb3-4019-859c-3780f21a25c5'")
print("Updated catalog_scope = 'all' for dsh key")

conn.commit()
conn.close()
print("Successfully configured OmniRoute permissions for andrei-router!")
