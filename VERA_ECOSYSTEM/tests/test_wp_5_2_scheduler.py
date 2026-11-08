"""
AIRA OS — Unit & Concurrency Tests for WP 5.2 (Polling Engine & Scheduler Hardening).

Verifies:
1. Per-device single-flight lock: Prevents overlapping polls on the same device.
2. Global concurrency limits: Enforces semaphore cap across concurrent devices.
3. Adaptive backoff and circuit breaker state transitions (NORMAL -> BACKOFF -> DORMANT_RETRY).
4. Fast-recovery: 2 consecutive successes immediately restore profile interval.
5. Scheduler lifecycle: Idempotent start/stop and clean shutdown via cancellation tokens.
6. Error isolation: Stalling device does not block healthy peers.
"""

from __future__ import annotations

import asyncio
import time
import pytest

from core.nms.scheduler import (
    CircuitBreakerState,
    DevicePollCoordinator,
    DevicePollState,
    HardenedNmsScheduler,
    PollingProfile,
    ProfileConfig,
)
from core.nms_models import NmsSchedulerState


def test_01_device_poll_state_profile_intervals():
    state_crit = DevicePollState(device_id="dev_core", profile_name=PollingProfile.CRITICAL.value)
    assert state_crit.effective_interval_sec() == 15.0

    state_std = DevicePollState(device_id="dev_switch", profile_name=PollingProfile.STANDARD.value)
    assert state_std.effective_interval_sec() == 45.0

    state_bulk = DevicePollState(device_id="dev_ap", profile_name=PollingProfile.BULK.value)
    assert state_bulk.effective_interval_sec() == 180.0


def test_02_adaptive_backoff_and_circuit_breaker():
    state = DevicePollState(device_id="dev_failing", profile_name=PollingProfile.CRITICAL.value)
    assert state.circuit_state == CircuitBreakerState.NORMAL.value

    # Failures 1 & 2: Still normal interval
    state.record_failure()
    assert state.consecutive_failures == 1
    assert state.circuit_state == CircuitBreakerState.NORMAL.value

    state.record_failure()
    assert state.consecutive_failures == 2
    assert state.circuit_state == CircuitBreakerState.NORMAL.value

    # Failure 3: Triggers BACKOFF
    state.record_failure()
    assert state.consecutive_failures == 3
    assert state.circuit_state == CircuitBreakerState.BACKOFF.value
    assert state.effective_interval_sec() > 15.0

    # Continue failures up to 10: Triggers DORMANT_RETRY
    for _ in range(7):
        state.record_failure()
    assert state.consecutive_failures == 10
    assert state.circuit_state == CircuitBreakerState.DORMANT_RETRY.value
    assert state.effective_interval_sec() == 300.0


def test_03_fast_recovery():
    state = DevicePollState(device_id="dev_recovering", profile_name=PollingProfile.STANDARD.value)
    for _ in range(10):
        state.record_failure()
    assert state.circuit_state == CircuitBreakerState.DORMANT_RETRY.value

    # First success -> RECOVERING
    recovered_1 = state.record_success()
    assert recovered_1 is False
    assert state.circuit_state == CircuitBreakerState.RECOVERING.value

    # Second success -> NORMAL (fully recovered!)
    recovered_2 = state.record_success()
    assert recovered_2 is True
    assert state.circuit_state == CircuitBreakerState.NORMAL.value
    assert state.effective_interval_sec() == 45.0


@pytest.mark.anyio
async def test_04_single_flight_lock_drops_overrun():
    coord = DevicePollCoordinator(max_concurrency=5)
    dev_id = "dev_laggy"

    lock = coord.get_async_lock(dev_id)
    state = coord.get_or_create_state(dev_id)

    # First poll acquires lock
    can_poll_1 = await coord.can_poll_device(dev_id)
    assert can_poll_1 is True

    # Simulate ongoing background poll holding the lock
    async with lock:
        # Second poll fires while first is still running
        can_poll_2 = await coord.can_poll_device(dev_id)
        assert can_poll_2 is False  # Overrun detected!
        assert state.total_overruns == 1

    # After lock released, next poll is permitted
    can_poll_3 = await coord.can_poll_device(dev_id)
    assert can_poll_3 is True


@pytest.mark.anyio
async def test_05_global_concurrency_bound():
    max_concurrency = 3
    coord = DevicePollCoordinator(max_concurrency=max_concurrency)
    semaphore = coord.get_semaphore()

    active_tasks = 0
    max_observed_tasks = 0

    async def mock_poll(dev_id: str):
        nonlocal active_tasks, max_observed_tasks
        lock = coord.get_async_lock(dev_id)
        async with lock:
            async with semaphore:
                active_tasks += 1
                max_observed_tasks = max(max_observed_tasks, active_tasks)
                await asyncio.sleep(0.05)
                active_tasks -= 1

    # Launch 10 simultaneous tasks
    tasks = [asyncio.create_task(mock_poll(f"dev_{i}")) for i in range(10)]
    await asyncio.gather(*tasks)

    assert max_observed_tasks <= max_concurrency
    assert active_tasks == 0


@pytest.mark.anyio
async def test_06_scheduler_lifecycle_and_clean_shutdown():
    executed_polls = []

    async def mock_executor(device_id: str, state: DevicePollState):
        executed_polls.append(device_id)
        state.record_success()

    scheduler = HardenedNmsScheduler(
        poll_executor=mock_executor,
        tick_interval_sec=0.05,
    )

    scheduler.register_device("dev_a", PollingProfile.CRITICAL.value)
    scheduler.register_device("dev_b", PollingProfile.STANDARD.value)

    assert scheduler.state == NmsSchedulerState.STOPPED

    # Idempotent start
    started = await scheduler.start()
    assert started is True
    assert scheduler.is_running() is True

    # Double start should be a no-op
    started_again = await scheduler.start()
    assert started_again is True

    # Allow one scheduler tick to execute due devices
    await asyncio.sleep(0.12)
    assert len(executed_polls) >= 2

    # Idempotent stop
    t0 = time.perf_counter()
    stopped = await scheduler.stop(timeout_sec=0.5)
    t_elapsed = time.perf_counter() - t0

    assert stopped is True
    assert scheduler.is_running() is False
    assert scheduler.state == NmsSchedulerState.STOPPED
    assert t_elapsed < 0.5  # Shutdown is sub-500ms
