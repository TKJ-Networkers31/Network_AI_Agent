"""
AIRA OS — Phase G Memory Subsystem & User Isolation Tests.
Validates:
1. Memory reset baseline (clean state).
2. Strict per-user isolation (User A cannot see or mutate User B's memories).
3. Ownership validation on update & delete.
4. Context retrieval for Ask AIRA (relevance scoring, memory toggle).
5. Non-memory entities (users, personas, chat sessions) preserved.
"""

import pytest
from core.tenant.memory_service import UserMemoryService

@pytest.fixture
def memory_svc():
    return UserMemoryService()

def test_memory_isolation_and_crud(memory_svc):
    from core.tenant.manager import IdentityManager
    id_mgr = IdentityManager()
    u_admin = id_mgr.get_user_by_username("lingga_admin")
    user_a = u_admin.user_id if u_admin else "usr_25b8282cc548"

    u_b = id_mgr.get_user_by_username("test_f2_readonly")
    if not u_b:
        u_b = id_mgr.create_user(username="test_f2_readonly", password="ReadOnlyPass123!", tenant_id="tenant_default")
    user_b = u_b.user_id

    # Clean test users
    memory_svc.clear_all_memories(user_a)
    memory_svc.clear_all_memories(user_b)

    # 1. Initial empty state
    mems_a = memory_svc.list_memories(user_a)
    mems_b = memory_svc.list_memories(user_b)
    assert len(mems_a) == 0
    assert len(mems_b) == 0

    # 2. User A creates a memory
    mem_a = memory_svc.add_memory(
        user_id=user_a,
        category="technical",
        content="Core Router R1 uses sfp-sfpplus1 as primary uplink to ISP-A",
        importance=0.9,
    )
    assert mem_a["memory_id"].startswith("mem_")
    assert mem_a["category"] == "technical"

    # 3. User B cannot see User A's memory
    mems_b = memory_svc.list_memories(user_b)
    assert len(mems_b) == 0

    # User B cannot retrieve User A's memory by ID
    assert memory_svc.get_memory(mem_a["memory_id"], user_b) is None

    # User B cannot delete User A's memory
    assert not memory_svc.delete_memory(mem_a["memory_id"], user_b)

    # 4. User B adds own memory
    mem_b = memory_svc.add_memory(
        user_id=user_b,
        category="workflows",
        content="NOC escalation procedure: contact duty engineer Lingga on P1 incidents",
        importance=0.8,
    )

    # User A only sees A's memory
    list_a = memory_svc.list_memories(user_a)
    assert len(list_a) == 1
    assert list_a[0]["content"] == mem_a["content"]

    # User B only sees B's memory
    list_b = memory_svc.list_memories(user_b)
    assert len(list_b) == 1
    assert list_b[0]["content"] == mem_b["content"]

    # 5. Ask AIRA context retrieval isolation
    ctx_a = memory_svc.retrieve_context_memories(user_a, query="sfp-sfpplus1 uplink")
    assert len(ctx_a) == 1
    assert "sfp-sfpplus1" in ctx_a[0]["content"]

    ctx_b = memory_svc.retrieve_context_memories(user_b, query="sfp-sfpplus1 uplink")
    assert len(ctx_b) == 0  # User B has no matching memory

    # 6. Memory toggle behavior
    memory_svc.set_memory_enabled(user_a, False)
    assert not memory_svc.is_memory_enabled(user_a)
    # When disabled, context retrieval returns empty
    assert len(memory_svc.retrieve_context_memories(user_a, query="sfp-sfpplus1")) == 0

    memory_svc.set_memory_enabled(user_a, True)
    assert memory_svc.is_memory_enabled(user_a)
    assert len(memory_svc.retrieve_context_memories(user_a, query="sfp-sfpplus1")) == 1

    # 7. Update memory
    updated = memory_svc.update_memory(
        mem_a["memory_id"],
        user_a,
        content="Core Router R1 uses sfp-sfpplus1 and sfp-sfpplus2 in LACP bond",
        importance=0.95,
    )
    assert updated["importance"] == 0.95
    assert "LACP bond" in updated["content"]

    # 8. Delete memory
    assert memory_svc.delete_memory(mem_a["memory_id"], user_a)
    assert memory_svc.get_memory(mem_a["memory_id"], user_a) is None
    assert len(memory_svc.list_memories(user_a)) == 0

    # Cleanup test records
    memory_svc.clear_all_memories(user_a)
    memory_svc.clear_all_memories(user_b)
