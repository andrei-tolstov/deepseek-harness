import sqlite3
import json

db = '/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite'
conn = sqlite3.connect(db)
c = conn.cursor()

print("=== KEY_VALUE COMPRESSION ===")
for r in c.execute("SELECT namespace, key, value FROM key_value WHERE namespace LIKE '%compress%'").fetchall():
    print(r)

print("\n=== ALL KEY_VALUE WHERE KEY LIKE COMPRESS ===")
for r in c.execute("SELECT namespace, key, value FROM key_value WHERE key LIKE '%compress%'").fetchall():
    print(r)

print("\n=== TABLES IN DB ===")
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print([t for t in tables if 'compress' in t.lower() or 'cache' in t.lower() or 'setting' in t.lower() or 'combo' in t.lower()])

for t in [t for t in tables if 'compress' in t.lower() or 'combo' in t.lower()]:
    print(f"\n--- TABLE {t} ---")
    cols = [d[0] for d in c.execute(f"SELECT * FROM {t} LIMIT 1").description]
    print("Columns:", cols)
    for row in c.execute(f"SELECT * FROM {t}").fetchall():
        print(row)
