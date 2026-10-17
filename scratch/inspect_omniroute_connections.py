import sqlite3
import json

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

for r in c.execute("SELECT * FROM provider_connections WHERE id LIKE '%qwen%' OR id LIKE '%bonsai%'").fetchall():
    print("=== Connection ===")
    for k in r.keys():
        print(f"  {k}: {r[k]}")

print("\n=== Provider Nodes ===")
for r in c.execute("SELECT * FROM provider_nodes WHERE id LIKE '%qwen%' OR id LIKE '%bonsai%'").fetchall():
    for k in r.keys():
        print(f"  {k}: {r[k]}")
    print()

conn.close()
