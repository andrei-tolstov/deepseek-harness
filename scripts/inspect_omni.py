import sqlite3

db_path = '/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite'
con = sqlite3.connect(db_path)
cur = con.cursor()

relevant = [
    'providers', 'models', 'connections', 'endpoints', 'routes', 'targets',
    'provider_connections', 'api_keys', 'virtual_keys'
]

tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Matching tables:", [t for t in tables if any(k in t for k in ['prov', 'model', 'conn', 'route', 'endp', 'key'])])

for t in tables:
    if any(k in t.lower() for k in ['prov', 'model', 'conn', 'route', 'endp', 'target']):
        try:
            rows = cur.execute(f"SELECT * FROM {t}").fetchall()
            cols = [d[0] for d in cur.description]
            print(f"\n=== TABLE {t} ({len(rows)} rows) ===")
            print("Columns:", cols)
            for r in rows[:10]:
                print(r)
        except Exception as e:
            pass
