# AIRA OS — Phase Networking III
# Unified Command Execution Layer Specification

## 1. Executive Summary

This document specifies the architecture, request/result data contracts, and security enforcement mechanisms of the **Unified Command Execution Layer** (`core/network_intelligence/command_execution.py`), implemented under Work Package N3.3 of Phase Networking III.

The execution layer provides a hardened, audit-compliant entry point for all command execution requests across the entire fleet of network devices, guaranteeing that no command reaches physical or virtual network devices without passing strict 10-layer read-only validation.

---

## 2. Architecture & Data Contracts

### 2.1 Domain Models

```python
class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    REJECTED_SECURITY = "REJECTED_SECURITY"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TIMEOUT = "TIMEOUT"
    AUTH_FAILED = "AUTH_FAILED"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"

@dataclass
class CommandExecutionRequest:
    target: str
    command: str
    timeout_seconds: float = 10.0
    correlation_id: str = ""
    operator: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CommandExecutionResult:
    target: str
    command: str
    status: ExecutionStatus
    raw_output: str = ""
    sanitized_excerpt: str = ""
    error_message: str = ""
    execution_duration_ms: float = 0.0
    is_read_only: bool = True
    rejection_reason: str = ""
    correlation_id: str = ""
    timestamp: float = field(default_factory=time.time)
```

---

## 3. Mandatory 10-Layer Security Pipeline

Before any command is dispatched to SSH transport or connection management, `UnifiedCommandExecutor.execute()` invokes `validate_readonly_command()`.

If validation fails:
1. Status is immediately marked `ExecutionStatus.REJECTED_SECURITY`.
2. `is_read_only` is set to `False`.
3. `rejection_reason` is captured verbatim.
4. Transport is **never called**; zero network packets leave the host.
5. An audit warning is logged with target name and correlation ID.

---

## 4. Concurrent Batch Execution

The executor provides `execute_batch()`:
- Accepts a list of `CommandExecutionRequest` objects.
- Uses `ThreadPoolExecutor(max_workers=min(max_workers, len(requests)))`.
- Collects results concurrently while enforcing per-target safety.
- Returns `Dict[str, CommandExecutionResult]`.

---

## 5. Verification Evidence

- Implemented in: `AIRA_ECOSYSTEM/core/network_intelligence/command_execution.py`.
- Automated Unit Tests: `AIRA_ECOSYSTEM/tests/test_networking_iii_command_execution.py` (4 tests passed).
- Security Audit: Integrated with 63 offline RouterOS CLI hardening tests in `test_routeros_command_hardening.py`.
