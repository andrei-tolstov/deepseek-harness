import sqlite3
import json

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

row = c.execute("SELECT value FROM key_value WHERE key = 'openai-compatible-chat-qwen38-v100:conn-qwen38'").fetchone()
if row:
    val = json.loads(row[0])
    print(json.dumps(val, indent=2, ensure_ascii=False))

conn.close()
