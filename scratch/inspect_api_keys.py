import sqlite3

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

for r in c.execute("SELECT id, name, key, allowed_models, model_access_mode, allowed_connections, catalog_scope FROM api_keys").fetchall():
    print(dict(r))

conn.close()
