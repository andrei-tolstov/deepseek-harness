import sqlite3
import json

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== key_value table keys ===")
for row in c.execute("SELECT key FROM key_value WHERE key LIKE '%model%' OR key LIKE '%qwen%' OR key LIKE '%sync%'"):
    print(row[0])

print("\n=== checking key_value for synced models ===")
for row in c.execute("SELECT key, substr(value, 1, 200) FROM key_value"):
    if any(x in str(row) for x in ['qwen', 'synced', '262144']):
        print("Key:", row[0], "Val start:", row[1])

conn.close()
