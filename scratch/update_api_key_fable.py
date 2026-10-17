import sqlite3
import json

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

dsh_key_id = "b3f368c2-9fb3-4019-859c-3780f21a25c5"
r = c.execute("SELECT allowed_models, allowed_connections FROM api_keys WHERE id = ?", (dsh_key_id,)).fetchone()
if r:
    models = json.loads(r["allowed_models"] or "[]")
    conns = json.loads(r["allowed_connections"] or "[]")
    
    new_models = [
        "fable", "fable-cold-fusion-27b", "qwen3.8-fable",
        "fable/fable", "fable/fable-cold-fusion-27b", "fable/qwen3.8-fable", "fable/default", "fable/*"
    ]
    for m in new_models:
        if m not in models:
            models.append(m)
            
    if "conn-fable" not in conns:
        conns.append("conn-fable")
        
    c.execute("""
        UPDATE api_keys 
        SET allowed_models = ?, allowed_connections = ?
        WHERE id = ?
    """, (json.dumps(models), json.dumps(conns), dsh_key_id))
    print(f"Updated api_key {dsh_key_id} (dsh)")

conn.commit()
conn.close()
print("Done updating api_keys for fable")
