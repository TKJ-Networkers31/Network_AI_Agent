"""
AIRA OS — Internal Event Bus
============================

File:
    AIRA_ECOSYSTEM/core/events.py

Purpose:
    Central publish/subscribe event system for AIRA OS.

Architecture:
    Publisher
        |
        v
    EventBus
        |
        +--> Logger
        +--> WebSocket
        +--> Memory
        +--> Voice
        +--> Companion
        +--> Scheduler
        +--> Other subscribers

Core principles:
    1. Modules communicate through events, not direct callbacks.
    2. Every event has a correlation_id for end-to-end tracing.
    3. Every event has a unique event_id.
    4. Subscribers are isolated from each other.
    5. Subscriber failure must never crash the publisher.
    6. EventBus is thread-safe.
    7. Event payloads are immutable after creation.
    8. Sync and async publishers are both supported.
    9. Wildcard subscribers can observe every event.
    10. EventBus itself does not contain business logic.

Sprint 1 — Core Stabilization
-----------------------------
This module is intentionally infrastructure-only.

Do NOT put:
    - LLM reasoning
    - routing logic
    - tool execution
    - network logic
    - persona logic
    - memory retrieval
    - security decisions

inside this file.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import uuid

from dataclasses import dataclass, field
from datetime import datetime, timezone

from typing import (
    Any,
    Awaitable,
    Callable,
    Optional,
    Union,
)

from core.logger import get_logger, log_event


# ============================================================
# LOGGER
# ============================================================

logger = get_logger("eventbus")


# ============================================================
# CONSTANTS
# ============================================================

WILDCARD = "*"


# ============================================================
# STANDARD EVENT NAMES
# ============================================================

class EventNames:
    """
    Standard event names used across AIRA OS.

    Naming convention:

        <domain>.<action>

    Examples:

        chat.received
        thinking.start
        tool.start
        response.ready
    """

    # --------------------------------------------------------
    # CHAT
    # --------------------------------------------------------

    CHAT_RECEIVED = "chat.received"

    # --------------------------------------------------------
    # THINKING
    # --------------------------------------------------------

    THINKING_START = "thinking.start"
    THINKING_FINISH = "thinking.finish"

    # --------------------------------------------------------
    # TOOL
    # --------------------------------------------------------

    TOOL_START = "tool.start"
    TOOL_PROGRESS = "tool.progress"
    TOOL_FINISH = "tool.finish"

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    RESPONSE_READY = "response.ready"

    # --------------------------------------------------------
    # MEMORY
    # --------------------------------------------------------

    MEMORY_SAVED = "memory.saved"

    # --------------------------------------------------------
    # SYSTEM
    # --------------------------------------------------------

    SYSTEM_ERROR = "system.error"

    # --------------------------------------------------------
    # MODEL
    # --------------------------------------------------------

    MODEL_STARTED = "model.started"
    MODEL_FINISHED = "model.finished"
    MODEL_FAILED = "model.failed"
    MODEL_SWITCHED = "model.switched"

    # --------------------------------------------------------
    # TASK
    # --------------------------------------------------------

    TASK_CLASSIFIED = "task.classified"
    TASK_STARTED = "task.started"
    TASK_FINISHED = "task.finished"

    LOCATION_UPDATED = "location.updated"
    LOCATION_CLEARED = "location.cleared"


# ============================================================
# STANDARD EVENT REGISTRY
# ============================================================

STANDARD_EVENTS: frozenset[str] = frozenset(
    {
        EventNames.CHAT_RECEIVED,

        EventNames.THINKING_START,
        EventNames.THINKING_FINISH,

        EventNames.TOOL_START,
        EventNames.TOOL_PROGRESS,
        EventNames.TOOL_FINISH,

        EventNames.RESPONSE_READY,

        EventNames.MEMORY_SAVED,

        EventNames.SYSTEM_ERROR,

        EventNames.MODEL_STARTED,
        EventNames.MODEL_FINISHED,
        EventNames.MODEL_FAILED,
        EventNames.MODEL_SWITCHED,

        EventNames.TASK_CLASSIFIED,
        EventNames.TASK_STARTED,
        EventNames.TASK_FINISHED,

        EventNames.LOCATION_UPDATED,
        EventNames.LOCATION_CLEARED,
    }
)


# ============================================================
# TYPE DEFINITIONS
# ============================================================

EventCallback = Callable[
    ["Event"],
    Union[
        None,
        Awaitable[None],
    ],
]


# ============================================================
# EVENT
# ============================================================

@dataclass(frozen=True)
class Event:
    """
    Immutable event contract.

    Example:

        Event(
            event="tool.start",
            correlation_id="abc123",
            source="AKANE",
            agent="AKANE",
            tool="ssh",
            data={
                "device": "R1",
                "command": "/system resource print",
            },
        )

    Serialized form:

        {
            "event_id": "...",
            "correlation_id": "...",
            "event": "tool.start",
            "source": "AKANE",
            "agent": "AKANE",
            "tool": "ssh",
            "timestamp": "...",
            "data": {...},
            "metadata": {...}
        }
    """

    # --------------------------------------------------------
    # IDENTIFIERS
    # --------------------------------------------------------

    event_id: str = field(
        default_factory=lambda: uuid.uuid4().hex
    )

    correlation_id: str = field(
        default_factory=lambda: uuid.uuid4().hex
    )

    # --------------------------------------------------------
    # EVENT INFORMATION
    # --------------------------------------------------------

    event: str = ""

    # --------------------------------------------------------
    # SOURCE
    # --------------------------------------------------------

    source: Optional[str] = None

    # --------------------------------------------------------
    # OPTIONAL AGENT / TOOL
    # --------------------------------------------------------

    agent: Optional[str] = None

    tool: Optional[str] = None

    # --------------------------------------------------------
    # TIMESTAMP
    # --------------------------------------------------------

    timestamp: str = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        ).isoformat()
    )

    # --------------------------------------------------------
    # PAYLOAD
    # --------------------------------------------------------

    data: dict[str, Any] = field(
        default_factory=dict
    )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # ========================================================
    # SERIALIZATION
    # ========================================================

    def to_dict(self) -> dict[str, Any]:
        """
        Convert event into a JSON-friendly dictionary.
        """

        return {
            "event_id": self.event_id,
            "correlation_id": self.correlation_id,
            "event": self.event,
            "source": self.source,
            "agent": self.agent,
            "tool": self.tool,
            "timestamp": self.timestamp,
            "data": self.data,
            "metadata": self.metadata,
        }

    # ========================================================
    # CORRELATION CHILD EVENT
    # ========================================================

    def child(
        self,
        event: str,
        *,
        source: Optional[str] = None,
        agent: Optional[str] = None,
        tool: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "Event":
        """
        Create another event while preserving the same
        correlation_id.

        Useful for tracing:

            chat.received
                |
                +--> thinking.start
                |
                +--> task.classified
                |
                +--> model.started
                |
                +--> tool.start
                |
                +--> tool.finish
                |
                +--> response.ready

        All events can share one correlation_id.
        """

        return Event(
            event=event,
            correlation_id=self.correlation_id,
            source=source or self.source,
            agent=agent if agent is not None else self.agent,
            tool=tool if tool is not None else self.tool,
            data=data or {},
            metadata=metadata or {},
        )


# ============================================================
# SUBSCRIPTION
# ============================================================

@dataclass(frozen=True)
class _Subscription:
    """
    Internal subscriber record.
    """

    token: str

    callback: EventCallback


# ============================================================
# EVENT BUS
# ============================================================

class EventBus:
    """
    Thread-safe publish/subscribe Event Bus.

    Responsibilities:

        publish
        subscribe
        unsubscribe
        event tracing
        subscriber isolation
        sync/async dispatch

    Non-responsibilities:

        reasoning
        routing
        execution
        security
        persistence
        business logic
    """

    def __init__(self) -> None:

        # ----------------------------------------------------
        # Subscriber registry
        # ----------------------------------------------------

        self._subscribers: dict[
            str,
            list[_Subscription],
        ] = {}

        # ----------------------------------------------------
        # Thread safety
        # ----------------------------------------------------

        self._lock = threading.RLock()

        # ----------------------------------------------------
        # Statistics
        # ----------------------------------------------------

        self._published_count = 0

        self._failed_callbacks = 0

    # ========================================================
    # SUBSCRIBE
    # ========================================================

    def subscribe(
        self,
        event_name: str,
        callback: EventCallback,
    ) -> str:
        """
        Register a callback.

        Example:

            token = event_bus.subscribe(
                EventNames.TOOL_START,
                handle_tool_start,
            )

        Wildcard:

            token = event_bus.subscribe(
                WILDCARD,
                handle_everything,
            )

        Returns:
            subscription token
        """

        if not event_name:
            raise ValueError(
                "event_name tidak boleh kosong."
            )

        if not callable(callback):
            raise TypeError(
                "callback harus callable."
            )

        token = uuid.uuid4().hex

        subscription = _Subscription(
            token=token,
            callback=callback,
        )

        with self._lock:

            if event_name not in self._subscribers:
                self._subscribers[event_name] = []

            self._subscribers[event_name].append(
                subscription
            )

            total = len(
                self._subscribers[event_name]
            )

        logger.debug(
            "SUBSCRIBE | event=%s | token=%s | total=%d",
            event_name,
            token,
            total,
        )

        return token

    # ========================================================
    # UNSUBSCRIBE
    # ========================================================

    def unsubscribe(
        self,
        event_name: str,
        token: str,
    ) -> bool:
        """
        Remove subscriber by token.
        """

        with self._lock:

            subscriptions = self._subscribers.get(
                event_name
            )

            if not subscriptions:
                return False

            remaining = [
                sub
                for sub in subscriptions
                if sub.token != token
            ]

            removed = (
                len(remaining)
                != len(subscriptions)
            )

            if remaining:

                self._subscribers[
                    event_name
                ] = remaining

            else:

                self._subscribers.pop(
                    event_name,
                    None,
                )

        if removed:

            logger.debug(
                "UNSUBSCRIBE | event=%s | token=%s",
                event_name,
                token,
            )

        return removed

    # ========================================================
    # CLEAR
    # ========================================================

    def clear(
        self,
        event_name: Optional[str] = None,
    ) -> None:
        """
        Remove subscribers.

        clear():
            remove everything

        clear("tool.start"):
            remove only tool.start subscribers
        """

        with self._lock:

            if event_name is None:

                self._subscribers.clear()

            else:

                self._subscribers.pop(
                    event_name,
                    None,
                )

    # ========================================================
    # PUBLISH
    # ========================================================

    def publish(
        self,
        event_name: str,
        *,
        correlation_id: Optional[str] = None,
        source: Optional[str] = None,
        agent: Optional[str] = None,
        tool: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Event:
        """
        Publish an event.

        This method is intentionally synchronous.

        It is safe to call from:

            - normal Python code
            - FastAPI
            - worker threads
            - SSH tools
            - planner
            - background tasks

        Async subscribers are scheduled/executed automatically.
        """

        if not event_name:

            raise ValueError(
                "event_name tidak boleh kosong."
            )

        event = Event(
            event=event_name,

            correlation_id=(
                correlation_id
                or uuid.uuid4().hex
            ),

            source=source,

            agent=agent,

            tool=tool,

            data=dict(data or {}),

            metadata=dict(metadata or {}),
        )

        # ----------------------------------------------------
        # Statistics
        # ----------------------------------------------------

        with self._lock:

            self._published_count += 1

        # ----------------------------------------------------
        # Internal logging
        # ----------------------------------------------------

        self._log_event(event)

        # ----------------------------------------------------
        # Dispatch
        # ----------------------------------------------------

        self._dispatch(event)

        return event

    # ========================================================
    # ASYNC PUBLISH
    # ========================================================

    async def publish_async(
        self,
        event_name: str,
        *,
        correlation_id: Optional[str] = None,
        source: Optional[str] = None,
        agent: Optional[str] = None,
        tool: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Event:
        """
        Async version of publish().

        Unlike publish(), this method waits until all subscribers
        have finished.

        Useful when event ordering matters.
        """

        if not event_name:

            raise ValueError(
                "event_name tidak boleh kosong."
            )

        event = Event(
            event=event_name,

            correlation_id=(
                correlation_id
                or uuid.uuid4().hex
            ),

            source=source,

            agent=agent,

            tool=tool,

            data=dict(data or {}),

            metadata=dict(metadata or {}),
        )

        with self._lock:

            self._published_count += 1

        self._log_event(event)

        await self._dispatch_async(event)

        return event

    # ========================================================
    # LOGGING
    # ========================================================

    def _log_event(
        self,
        event: Event,
    ) -> None:
        """
        Internal event logging.

        Logging failure must NEVER break EventBus.
        """

        try:

            log_event(
                logger,
                "DEBUG",
                f"EVENT | {event.event}",
                category="eventbus",
                context=event.to_dict(),
            )

        except Exception:

            logger.exception(
                "EventBus logging gagal "
                "(diabaikan)."
            )

    # ========================================================
    # COLLECT SUBSCRIBERS
    # ========================================================

    def _collect_subscriptions(
        self,
        event_name: str,
    ) -> list[_Subscription]:
        """
        Return a snapshot of subscribers.

        Snapshot prevents mutation of the subscriber registry
        while dispatching.
        """

        with self._lock:

            specific = list(
                self._subscribers.get(
                    event_name,
                    [],
                )
            )

            wildcard = list(
                self._subscribers.get(
                    WILDCARD,
                    [],
                )
            )

        return specific + wildcard

    # ========================================================
    # SYNC DISPATCH
    # ========================================================

    def _dispatch(
        self,
        event: Event,
    ) -> None:
        """
        Dispatch event from synchronous code.
        """

        subscriptions = (
            self._collect_subscriptions(
                event.event
            )
        )

        if not subscriptions:
            return

        # ----------------------------------------------------
        # Detect active asyncio loop
        # ----------------------------------------------------

        try:

            loop = asyncio.get_running_loop()

        except RuntimeError:

            loop = None

        # ----------------------------------------------------
        # Active async loop
        # ----------------------------------------------------

        if loop is not None:

            for subscription in subscriptions:

                task = loop.create_task(
                    self._run_callback(
                        subscription,
                        event,
                    )
                )

                # Make sure task exception is consumed.
                task.add_done_callback(
                    self._consume_task_result
                )

            return

        # ----------------------------------------------------
        # Pure sync context
        # ----------------------------------------------------

        asyncio.run(
            self._dispatch_async(
                event,
                subscriptions,
            )
        )

    # ========================================================
    # ASYNC DISPATCH
    # ========================================================

    async def _dispatch_async(
        self,
        event: Event,
        subscriptions: Optional[
            list[_Subscription]
        ] = None,
    ) -> None:
        """
        Dispatch all subscribers concurrently.
        """

        if subscriptions is None:

            subscriptions = (
                self._collect_subscriptions(
                    event.event
                )
            )

        if not subscriptions:
            return

        await asyncio.gather(
            *(
                self._run_callback(
                    subscription,
                    event,
                )
                for subscription in subscriptions
            ),
            return_exceptions=True,
        )

    # ========================================================
    # CALLBACK EXECUTOR
    # ========================================================

    async def _run_callback(
        self,
        subscription: _Subscription,
        event: Event,
    ) -> None:
        """
        Execute one subscriber safely.

        Supports:

            def callback(event):
                ...

        and:

            async def callback(event):
                ...
        """

        try:

            result = subscription.callback(
                event
            )

            # ------------------------------------------------
            # Async callback
            # ------------------------------------------------

            if inspect.isawaitable(result):

                await result

        except Exception:

            with self._lock:

                self._failed_callbacks += 1

            logger.exception(
                "EVENT SUBSCRIBER ERROR | "
                "event=%s | "
                "event_id=%s | "
                "correlation_id=%s | "
                "token=%s",
                event.event,
                event.event_id,
                event.correlation_id,
                subscription.token,
            )

    # ========================================================
    # TASK RESULT CONSUMER
    # ========================================================

    @staticmethod
    def _consume_task_result(
        task: asyncio.Task,
    ) -> None:
        """
        Consume task result so background subscriber
        exceptions never become unhandled asyncio warnings.
        """

        try:

            task.result()

        except asyncio.CancelledError:

            pass

        except Exception:

            # _run_callback already handles subscriber errors.
            pass

    # ========================================================
    # INSPECTION
    # ========================================================

    def subscriber_count(
        self,
        event_name: Optional[str] = None,
    ) -> int:
        """
        Return subscriber count.

        subscriber_count():
            all subscribers

        subscriber_count("tool.start"):
            subscribers for tool.start
        """

        with self._lock:

            if event_name is not None:

                return len(
                    self._subscribers.get(
                        event_name,
                        [],
                    )
                )

            return sum(
                len(subscribers)
                for subscribers
                in self._subscribers.values()
            )

    # ========================================================
    # STATS
    # ========================================================

    def stats(self) -> dict[str, int]:
        """
        Return basic EventBus statistics.
        """

        with self._lock:

            return {
                "published": self._published_count,
                "failed_callbacks": (
                    self._failed_callbacks
                ),
                "subscriber_count": (
                    self.subscriber_count()
                ),
            }

    # ========================================================
    # RESET STATS
    # ========================================================

    def reset_stats(self) -> None:
        """
        Reset runtime statistics.

        Mostly useful for tests.
        """

        with self._lock:

            self._published_count = 0
            self._failed_callbacks = 0


# ============================================================
# GLOBAL SINGLETON
# ============================================================

event_bus = EventBus()


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def publish_event(
    event_name: str,
    *,
    correlation_id: Optional[str] = None,
    source: Optional[str] = None,
    agent: Optional[str] = None,
    tool: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> Event:
    """
    Convenience wrapper.

    Instead of:

        event_bus.publish(...)

    You can use:

        publish_event(...)
    """

    return event_bus.publish(
        event_name,
        correlation_id=correlation_id,
        source=source,
        agent=agent,
        tool=tool,
        data=data,
        metadata=metadata,
    )


async def publish_event_async(
    event_name: str,
    *,
    correlation_id: Optional[str] = None,
    source: Optional[str] = None,
    agent: Optional[str] = None,
    tool: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> Event:
    """
    Async convenience wrapper.
    """

    return await event_bus.publish_async(
        event_name,
        correlation_id=correlation_id,
        source=source,
        agent=agent,
        tool=tool,
        data=data,
        metadata=metadata,
    )


# ============================================================
# EXAMPLE
# ============================================================

if __name__ == "__main__":

    def logger_listener(event: Event) -> None:

        print(
            "[EVENT]",
            event.event,
            event.correlation_id,
        )

    async def websocket_listener(
        event: Event,
    ) -> None:

        print(
            "[WS]",
            event.event,
            event.event_id,
        )

    # --------------------------------------------------------
    # Subscribe
    # --------------------------------------------------------

    event_bus.subscribe(
        WILDCARD,
        logger_listener,
    )

    event_bus.subscribe(
        EventNames.TOOL_START,
        websocket_listener,
    )

    # --------------------------------------------------------
    # Publish
    # --------------------------------------------------------

    correlation_id = uuid.uuid4().hex

    event_bus.publish(
        EventNames.TOOL_START,
        correlation_id=correlation_id,
        source="AKANE",
        agent="AKANE",
        tool="ssh",
        data={
            "device": "R1",
            "command": "/system resource print",
        },
        metadata={
            "environment": "lab",
        },
    )

    # --------------------------------------------------------
    # Stats
    # --------------------------------------------------------

    print(
        event_bus.stats()
    )