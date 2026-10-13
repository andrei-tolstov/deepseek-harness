import sqlite3
import json

db_path = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

def print_table(tbl):
    print(f"\n=== Table: {tbl} ===")
    cols = [col[1] for col in c.execute(f"PRAGMA table_info({tbl})").fetchall()]
    print("Columns:", cols)
    for row in c.execute(f"SELECT * FROM {tbl}").fetchall():
        row_dict = dict(zip(cols, row))
        # print if relevant
        str_row = str(row_dict)
        if any(x in str_row for x in ['qwen', 'default', '262144', '180000']):
            print("Row:", row_dict)

print_table("model_context_overrides")
print_table("provider_connections")
print_table("provider_nodes")

conn.close()
