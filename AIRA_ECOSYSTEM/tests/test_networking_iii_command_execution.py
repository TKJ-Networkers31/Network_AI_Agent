"""
tests/test_networking_iii_command_execution.py — Unit tests for Phase Networking III Unified Command Execution.
"""

import pytest
from core.network_intelligence.command_execution import (
    CommandExecutionRequest,
    CommandExecutionResult,
    ExecutionStatus,
    UnifiedCommandExecutor,
)


def test_command_execution_request_and_result_dataclass():
    req = CommandExecutionRequest(
        device_id="CHR",
        command_str="/system identity print",
        observation_domain="identity",
        timeout=10.0,
    )
    req_dict = req.to_dict()
    assert req_dict["device_id"] == "CHR"
    assert req_dict["command_str"] == "/system identity print"
    assert req_dict["observation_domain"] == "identity"
    assert req_dict["timeout"] == 10.0
    assert "request_id" in req_dict

    res = CommandExecutionResult(
        request_id=req.request_id,
        device_id="CHR",
        command_str=req.command_str,
        execution_status=ExecutionStatus.SUCCESS,
        start_timestamp=100.0,
        completion_timestamp=100.05,
        duration_ms=50.0,
        raw_output="name: CHR",
    )
    assert res.is_success is True
    res_dict = res.to_dict()
    assert res_dict["execution_status"] == "SUCCESS"
    assert res_dict["duration_ms"] == 50.0
    assert "name: CHR" in res_dict["raw_output"]


def test_command_executor_security_rejection_before_transport():
    executor = UnifiedCommandExecutor()

    # 1. Mutating verb
    bad_req1 = CommandExecutionRequest(
        device_id="CHR",
        command_str="/system reboot",
        observation_domain="system",
    )
    res1 = executor.execute(bad_req1)
    assert res1.execution_status == ExecutionStatus.SECURITY_REJECTED
    assert res1.is_success is False
    assert res1.error_classification == "SECURITY_POLICY_VIOLATION"
    assert "[SECURITY_REJECTED]" in res1.raw_output

    # 2. Delimiter injection
    bad_req2 = CommandExecutionRequest(
        device_id="CHR",
        command_str="/system identity print; /user add name=hacker",
        observation_domain="system",
    )
    res2 = executor.execute(bad_req2)
    assert res2.execution_status == ExecutionStatus.SECURITY_REJECTED
    assert res2.error_classification == "SECURITY_POLICY_VIOLATION"


def test_command_executor_target_not_found():
    executor = UnifiedCommandExecutor()
    req = CommandExecutionRequest(
        device_id="phantom_device_xyz",
        command_str="/system identity print",
    )
    res = executor.execute(req)
    assert res.execution_status == ExecutionStatus.FAILED
    assert res.error_classification == "TARGET_NOT_FOUND"


def test_command_executor_batch_execution():
    executor = UnifiedCommandExecutor()
    reqs = [
        CommandExecutionRequest(device_id="phantom_1", command_str="/system identity print"),
        CommandExecutionRequest(device_id="phantom_2", command_str="/system resource print"),
        CommandExecutionRequest(device_id="CHR", command_str="/system shutdown"),  # Rejected
    ]
    results = executor.execute_batch(reqs, max_concurrency=2)
    assert len(results) == 3

    # The 3rd request must be security rejected
    res_rejected = [r for r in results if r.command_str == "/system shutdown"][0]
    assert res_rejected.execution_status == ExecutionStatus.SECURITY_REJECTED
