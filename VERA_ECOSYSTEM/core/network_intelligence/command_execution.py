"""
core/network_intelligence/command_execution.py — Unified Command Execution Layer for AIRA OS.

Standardizes read-only observation command dispatch across multi-vendor network devices.
Enforces strict 10-layer AST read-only validation prior to any transport transmission.
Retains complete execution provenance, duration, error classification, and truncation tracking.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from agents.akane.connection_manager import ConnectionManager, get_connection_manager
from core.canonical_network import CanonicalNetworkRegistry, get_canonical_registry
from core.network_intelligence.security import validate_readonly_command
from core.topology_models import sanitize_cli_excerpt

logger = logging.getLogger("aira.network_intelligence.command_execution")


class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    SECURITY_REJECTED = "SECURITY_REJECTED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class CommandExecutionRequest:
    device_id: str
    command_str: str
    observation_domain: str = "general"
    command_args: Optional[List[str]] = None
    timeout: float = 25.0
    request_id: str = field(default_factory=lambda: f"cmd_{uuid.uuid4().hex[:10]}")
    execution_timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "device_id": self.device_id,
            "command_str": self.command_str,
            "observation_domain": self.observation_domain,
            "command_args": self.command_args,
            "timeout": self.timeout,
            "execution_timestamp": self.execution_timestamp,
        }


@dataclass
class CommandExecutionResult:
    request_id: str
    device_id: str
    command_str: str
    execution_status: ExecutionStatus
    start_timestamp: float
    completion_timestamp: float
    duration_ms: float
    raw_output: str = ""
    parsed_result: Optional[Any] = None
    error_classification: Optional[str] = None
    truncated: bool = False

    @property
    def is_success(self) -> bool:
        return self.execution_status == ExecutionStatus.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "device_id": self.device_id,
            "command_str": self.command_str,
            "execution_status": self.execution_status.value,
            "start_timestamp": self.start_timestamp,
            "completion_timestamp": self.completion_timestamp,
            "duration_ms": self.duration_ms,
            "raw_output": sanitize_cli_excerpt(self.raw_output, max_len=1500),
            "parsed_result": self.parsed_result,
            "error_classification": self.error_classification,
            "truncated": self.truncated,
        }


class UnifiedCommandExecutor:
    """
    Standardized command execution manager.
    Coordinates allowlist validation, target resolution, and controlled transport dispatch.
    """

    def __init__(
        self,
        connection_manager: Optional[ConnectionManager] = None,
        registry: Optional[CanonicalNetworkRegistry] = None,
    ):
        self.cm = connection_manager or get_connection_manager()
        self.registry = registry or get_canonical_registry()

    def execute(self, req: CommandExecutionRequest) -> CommandExecutionResult:
        """
        Executes a single observation command under strict read-only controls.
        """
        t_start = time.time()

        # 1. Mandatory Read-Only Policy Validation
        is_valid, reason = validate_readonly_command(req.command_str)
        if not is_valid:
            t_end = time.time()
            logger.warning(
                "UnifiedCommandExecutor | Command rejected by security boundary: '%s' (Reason: %s)",
                req.command_str,
                reason,
            )
            return CommandExecutionResult(
                request_id=req.request_id,
                device_id=req.device_id,
                command_str=req.command_str,
                execution_status=ExecutionStatus.SECURITY_REJECTED,
                start_timestamp=t_start,
                completion_timestamp=t_end,
                duration_ms=round((t_end - t_start) * 1000, 2),
                raw_output=f"[SECURITY_REJECTED] {reason}",
                error_classification="SECURITY_POLICY_VIOLATION",
                truncated=False,
            )

        # 2. Resolve target device
        resolved_dev = self.registry.resolve_device(req.device_id)
        target_name = resolved_dev.inventory_name if (resolved_dev and resolved_dev.inventory_name) else req.device_id

        # 3. Transport Dispatch
        try:
            res = self.cm.execute_command(
                command=req.command_str,
                device_name=target_name,
                timeout=req.timeout,
            )
            t_end = time.time()
            dur_ms = round((t_end - t_start) * 1000, 2)

            if res.get("success"):
                out = res.get("output", "")
                is_trunc = "[truncated]" in out.lower()
                return CommandExecutionResult(
                    request_id=req.request_id,
                    device_id=req.device_id,
                    command_str=req.command_str,
                    execution_status=ExecutionStatus.SUCCESS,
                    start_timestamp=t_start,
                    completion_timestamp=t_end,
                    duration_ms=dur_ms,
                    raw_output=out,
                    error_classification=None,
                    truncated=is_trunc,
                )
            else:
                err_msg = res.get("error", "Unknown execution error")
                status = ExecutionStatus.FAILED
                err_class = "EXECUTION_ERROR"
                if "timed out" in err_msg.lower() or "timeout" in err_msg.lower():
                    status = ExecutionStatus.TIMEOUT
                    err_class = "SOCKET_TIMEOUT"
                elif "tidak ditemukan" in err_msg.lower():
                    err_class = "TARGET_NOT_FOUND"

                return CommandExecutionResult(
                    request_id=req.request_id,
                    device_id=req.device_id,
                    command_str=req.command_str,
                    execution_status=status,
                    start_timestamp=t_start,
                    completion_timestamp=t_end,
                    duration_ms=dur_ms,
                    raw_output=f"[ERROR] {err_msg}",
                    error_classification=err_class,
                    truncated=False,
                )

        except Exception as exc:
            t_end = time.time()
            return CommandExecutionResult(
                request_id=req.request_id,
                device_id=req.device_id,
                command_str=req.command_str,
                execution_status=ExecutionStatus.FAILED,
                start_timestamp=t_start,
                completion_timestamp=t_end,
                duration_ms=round((t_end - t_start) * 1000, 2),
                raw_output=f"[EXCEPTION] {str(exc)}",
                error_classification="UNHANDLED_EXCEPTION",
                truncated=False,
            )

    def execute_batch(
        self,
        requests: List[CommandExecutionRequest],
        max_concurrency: int = 3,
    ) -> List[CommandExecutionResult]:
        """
        Executes a batch of CommandExecutionRequests concurrently using a bounded thread pool.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if not requests:
            return []

        concurrency = max(1, min(max_concurrency, len(requests)))
        results: List[Optional[CommandExecutionResult]] = [None] * len(requests)

        def _worker(idx: int, r: CommandExecutionRequest) -> tuple[int, CommandExecutionResult]:
            return idx, self.execute(r)

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_to_idx = {executor.submit(_worker, i, r): i for i, r in enumerate(requests)}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    _, res = future.result()
                    results[idx] = res
                except Exception as exc:
                    results[idx] = CommandExecutionResult(
                        request_id=requests[idx].request_id,
                        device_id=requests[idx].device_id,
                        command_str=requests[idx].command_str,
                        execution_status=ExecutionStatus.FAILED,
                        start_timestamp=time.time(),
                        completion_timestamp=time.time(),
                        duration_ms=0.0,
                        raw_output=f"[EXCEPTION] {str(exc)}",
                        error_classification="BATCH_THREAD_EXCEPTION",
                        truncated=False,
                    )

        return [r for r in results if r is not None]
