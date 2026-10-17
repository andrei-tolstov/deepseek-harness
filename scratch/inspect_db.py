import sqlite3
import json

conn = sqlite3.connect('hermes_state.db')
cur = conn.cursor()

cur.execute('SELECT DISTINCT tool_name FROM messages WHERE tool_name IS NOT NULL')
print('Tool names in tool turns:', [r[0] for r in cur.fetchall()])

cur.execute('SELECT tool_calls FROM messages WHERE tool_calls IS NOT NULL')
funcs = set()
for (tc_json,) in cur.fetchall():
    try:
        tcs = json.loads(tc_json)
        for tc in tcs:
            fn = tc.get('function', {}).get('name')
            if fn:
                funcs.add(fn)
    except Exception as e:
        pass
print('Functions invoked in assistant turns:', funcs)

cur.execute('SELECT DISTINCT session_id FROM messages')
sessions = [r[0] for r in cur.fetchall()]
print('Sessions count:', len(sessions), sessions)
