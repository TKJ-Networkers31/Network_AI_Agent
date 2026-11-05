import sqlite3

conn = sqlite3.connect('AIRA_ECOSYSTEM/database/inventory.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table';")
print('inventory tables:', c.fetchall())

try:
    for row in c.execute("SELECT id, name, host, port, username FROM devices"):
        print('device:', row)
except Exception as e:
    print('error querying devices:', e)

conn.close()
