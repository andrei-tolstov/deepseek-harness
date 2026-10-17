import sqlite3

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("=== model_capabilities ===")
for r in c.execute("SELECT * FROM model_capabilities WHERE provider LIKE '%qwen%' OR provider LIKE '%bonsai%'").fetchall():
    print(dict(r))

print("=== model_capability_overrides ===")
for r in c.execute("SELECT * FROM model_capability_overrides WHERE provider LIKE '%qwen%' OR provider LIKE '%bonsai%'").fetchall():
    print(dict(r))

print("=== model_context_overrides ===")
for r in c.execute("SELECT * FROM model_context_overrides WHERE provider LIKE '%qwen%' OR provider LIKE '%bonsai%'").fetchall():
    print(dict(r))

conn.close()
