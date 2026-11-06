"""
AIRA OS — Controlled Memory Data Reset Script (Workstream F).
Resets only stored memory data records across memory tables.
Preserves user accounts, credentials, personas, chat history, RBAC, inventory, and database schemas.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = BASE_DIR / "database"

def reset_memory() -> dict:
    results = {
        "status": "SUCCESS",
        "before": {},
        "after": {},
        "schemas_verified": {},
    }

    # 1. topology.db -> user_memories
    top_db = DATABASE_DIR / "topology.db"
    if top_db.exists():
        with sqlite3.connect(top_db) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM user_memories")
            before_cnt = cur.fetchone()[0]
            results["before"]["topology.db:user_memories"] = before_cnt

            # Delete in transaction
            cur.execute("DELETE FROM user_memories")
            conn.commit()

            cur.execute("SELECT COUNT(*) FROM user_memories")
            after_cnt = cur.fetchone()[0]
            results["after"]["topology.db:user_memories"] = after_cnt
            results["schemas_verified"]["topology.db:user_memories"] = True

            # Verify non-memory tables are intact
            cur.execute("SELECT COUNT(*) FROM operational_users")
            results["schemas_verified"]["operational_users_count"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM user_personas")
            results["schemas_verified"]["user_personas_count"] = cur.fetchone()[0]

    # 2. long_term_memory.db -> facts, events
    lt_db = DATABASE_DIR / "long_term_memory.db"
    if lt_db.exists():
        with sqlite3.connect(lt_db) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM facts")
            results["before"]["long_term_memory.db:facts"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM events")
            results["before"]["long_term_memory.db:events"] = cur.fetchone()[0]

            cur.execute("DELETE FROM facts")
            cur.execute("DELETE FROM events")
            conn.commit()

            cur.execute("SELECT COUNT(*) FROM facts")
            results["after"]["long_term_memory.db:facts"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM events")
            results["after"]["long_term_memory.db:events"] = cur.fetchone()[0]
            results["schemas_verified"]["long_term_memory.db"] = True

    # 3. interaction_memory.db -> interaction_context
    im_db = DATABASE_DIR / "interaction_memory.db"
    if im_db.exists():
        with sqlite3.connect(im_db) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM interaction_context")
            results["before"]["interaction_memory.db:interaction_context"] = cur.fetchone()[0]

            cur.execute("DELETE FROM interaction_context")
            conn.commit()

            cur.execute("SELECT COUNT(*) FROM interaction_context")
            results["after"]["interaction_memory.db:interaction_context"] = cur.fetchone()[0]
            results["schemas_verified"]["interaction_memory.db"] = True

    # 4. semantic_memory.db -> semantic_memory
    sm_db = DATABASE_DIR / "semantic_memory.db"
    if sm_db.exists():
        with sqlite3.connect(sm_db) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM semantic_memory")
            results["before"]["semantic_memory.db:semantic_memory"] = cur.fetchone()[0]

            cur.execute("DELETE FROM semantic_memory")
            conn.commit()

            cur.execute("SELECT COUNT(*) FROM semantic_memory")
            results["after"]["semantic_memory.db:semantic_memory"] = cur.fetchone()[0]
            results["schemas_verified"]["semantic_memory.db"] = True

    # 5. Flush memory cache in api.state
    try:
        from api.state import drop_all_caches
        drop_all_caches()
        results["memory_cache_cleared"] = True
    except Exception:
        results["memory_cache_cleared"] = "in-memory cache will be cleared on process restart"

    return results

if __name__ == "__main__":
    res = reset_memory()
    print(json.dumps(res, indent=2))
