"""
AIRA OS — Non-Admin Users Cleanup Script
Purges all users, roles, memberships, and sessions except root administrator (lingga_admin).
"""

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "database" / "topology.db"


def cleanup():
    if not DB_PATH.exists():
        print("topology.db not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    with conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM operational_users WHERE username = 'lingga_admin'")
        row = c.fetchone()
        if not row:
            print("[ERROR] lingga_admin not found!")
            return
        admin_id = row[0]
        print(f"Found lingga_admin ID: {admin_id}")

        d_sessions = conn.execute("DELETE FROM operational_user_sessions WHERE user_id != ?", (admin_id,)).rowcount
        d_memberships = conn.execute("DELETE FROM operational_user_group_memberships WHERE user_id != ?", (admin_id,)).rowcount
        d_roles = conn.execute("DELETE FROM operational_user_roles WHERE user_id != ?", (admin_id,)).rowcount
        d_personas = conn.execute("DELETE FROM user_personas WHERE user_id != ?", (admin_id,)).rowcount
        d_activity = conn.execute("DELETE FROM operational_user_activity_events WHERE username != 'lingga_admin'").rowcount
        d_users = conn.execute("DELETE FROM operational_users WHERE user_id != ?", (admin_id,)).rowcount

        print(f"Deleted: {d_users} users, {d_roles} roles, {d_memberships} memberships, {d_sessions} sessions, {d_activity} activity events, {d_personas} personas")

        remaining = conn.execute("SELECT user_id, username, email FROM operational_users").fetchall()
        print("Remaining users:", remaining)


if __name__ == "__main__":
    cleanup()
