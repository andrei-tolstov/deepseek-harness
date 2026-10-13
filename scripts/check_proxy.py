import sqlite3

con = sqlite3.connect('/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite')
cur = con.cursor()

print("--- proxy_registry ---")
try:
    rows = cur.execute("SELECT * FROM proxy_registry").fetchall()
    cols = [d[0] for d in cur.description]
    print("Cols:", cols)
    print("Count:", len(rows))
    for r in rows:
        print(r)
except Exception as e:
    print("Err:", e)

print("--- key_value with proxy ---")
try:
    rows2 = cur.execute("SELECT namespace, key, value FROM key_value WHERE namespace LIKE '%proxy%' OR key LIKE '%proxy%'").fetchall()
    print("Count:", len(rows2))
    for r in rows2:
        print(r)
except Exception as e:
    print("Err:", e)

print("--- provider_connections proxy info ---")
try:
    rows3 = cur.execute("SELECT id, provider, name, proxy_enabled, per_key_proxy_enabled, last_error FROM provider_connections").fetchall()
    for r in rows3:
        print(r)
except Exception as e:
    print("Err:", e)
