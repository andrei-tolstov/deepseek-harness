import sqlite3

c = sqlite3.connect("/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite").cursor()
cols = [d[0] for d in c.execute("SELECT * FROM compression_cache_stats LIMIT 1").description]
print("Columns:", cols)
for r in c.execute("SELECT * FROM compression_cache_stats ORDER BY id DESC LIMIT 5").fetchall():
    print(dict(zip(cols, r)))
