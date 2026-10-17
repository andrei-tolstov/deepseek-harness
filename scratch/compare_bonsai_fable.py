import sqlite3

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("=== provider_nodes ===")
for r in c.execute("SELECT * FROM provider_nodes WHERE id LIKE '%bonsai%' OR id LIKE '%fable%'").fetchall():
    print(dict(r))

print("\n=== provider_connections ===")
for r in c.execute("SELECT * FROM provider_connections WHERE id LIKE '%bonsai%' OR id LIKE '%fable%'").fetchall():
    print(dict(r))

print("\n=== key_value syncedAvailableModels ===")
for r in c.execute("SELECT namespace, key, substr(value, 1, 200) as val_sub FROM key_value WHERE key LIKE '%bonsai%' OR key LIKE '%fable%'").fetchall():
    print(dict(r))

print("\n=== other tables referencing bonsai or fable ===")
tables = [row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for t in tables:
    if t in ['provider_nodes', 'provider_connections', 'key_value', 'call_logs', 'proxy_logs', 'model_context_overrides']:
        continue
    try:
        # Check if table has provider or model columns
        cols = [col[1] for col in c.execute(f"PRAGMA table_info({t})").fetchall()]
        for col in cols:
            q = f"SELECT count(*) FROM {t} WHERE cast({col} as text) LIKE '%bonsai%' OR cast({col} as text) LIKE '%fable%'"
            cnt = c.execute(q).fetchone()[0]
            if cnt > 0:
                print(f"Table {t}.{col} has {cnt} matches")
    except Exception as e:
        pass

conn.close()
