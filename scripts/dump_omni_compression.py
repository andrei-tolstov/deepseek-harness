import sqlite3
import json

db = '/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite'
conn = sqlite3.connect(db)
c = conn.cursor()

print("=== KEY_VALUE (compression) ===")
for r in c.execute("SELECT namespace, key, value FROM key_value WHERE namespace LIKE '%compress%'").fetchall():
    print(r[0], "->", r[1], ":", r[2])

print("\n=== COMPRESSION_COMBOS ===")
try:
    cols = [d[0] for d in c.execute("SELECT * FROM compression_combos LIMIT 1").description]
    print("Cols:", cols)
    for r in c.execute("SELECT * FROM compression_combos").fetchall():
        print(dict(zip(cols, r)))
except Exception as e:
    print(e)

print("\n=== COMPRESSION_COMBO_ASSIGNMENTS ===")
try:
    cols = [d[0] for d in c.execute("SELECT * FROM compression_combo_assignments LIMIT 1").description]
    print("Cols:", cols)
    for r in c.execute("SELECT * FROM compression_combo_assignments").fetchall():
        print(dict(zip(cols, r)))
except Exception as e:
    print(e)

print("\n=== RECENT STATS SUMMARY ===")
try:
    for r in c.execute("SELECT engine, sum(original_tokens), sum(compressed_tokens), sum(tokens_saved) FROM compression_cache_stats GROUP BY engine").fetchall():
        print("Engine:", r)
except Exception as e:
    print(e)
