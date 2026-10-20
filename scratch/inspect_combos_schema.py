import sqlite3

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

for t in ["combos", "model_combo_mappings", "domain_fallback_chains", "routing_decisions"]:
    print(f"\n=== Schema for {t} ===")
    for col in c.execute(f"PRAGMA table_info({t})").fetchall():
        print(col)

conn.close()
