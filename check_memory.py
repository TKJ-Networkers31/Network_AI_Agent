import sqlite3

conn = sqlite3.connect("data/long_term_memory.db")
conn.row_factory = sqlite3.Row

print("=== FACTS ===")
for row in conn.execute("SELECT key, value, updated_at FROM facts ORDER BY updated_at DESC"):
    print(dict(row))

print("\n=== EVENTS ===")
for row in conn.execute("SELECT * FROM events ORDER BY created_at DESC LIMIT 10"):
    print(dict(row))