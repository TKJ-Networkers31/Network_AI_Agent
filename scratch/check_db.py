import sqlite3
import os

db_path = r'AIRA_ECOSYSTEM/database/topology.db'
if not os.path.exists(db_path):
    print(f"Error: {db_path} does not exist")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# PRAGMA integrity_check
cur.execute('PRAGMA integrity_check;')
integrity = cur.fetchall()
print('integrity_check:', integrity)

# PRAGMA foreign_key_check
cur.execute('PRAGMA foreign_key_check;')
fk_check = cur.fetchall()
print('foreign_key_check:', fk_check)

# PRAGMA journal_mode
cur.execute('PRAGMA journal_mode;')
journal_mode = cur.fetchone()[0]
print('journal_mode:', journal_mode)

# List triggers
cur.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger';")
triggers = cur.fetchall()
print(f'Triggers found: {len(triggers)}')
for t in triggers:
    print(f' - Trigger: {t[0]} on table: {t[1]}')

# Check table count and sample counts
cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table';")
table_count = cur.fetchone()[0]
print('Table count:', table_count)

conn.close()
