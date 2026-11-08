"""
api/ws_manager.py — registry koneksi WebSocket AIRA, dikelompokkan per
session_id dan terisolasi per tenant_id (Workstream K).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger("aira.ws")


class ConnectionManager:

    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}
        self._session_tenants: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket, tenant_id: str = "tenant_internal") -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(session_id, []).append(websocket)
            self._session_tenants[session_id] = tenant_id
        logger.info("WS CONNECT | session=%s | tenant=%s | total_conn=%d", session_id, tenant_id, len(self._connections.get(session_id, [])))

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(session_id, [])
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                self._connections.pop(session_id, None)
                self._session_tenants.pop(session_id, None)
        logger.info("WS DISCONNECT | session=%s", session_id)

    async def send(self, session_id: str, payload: dict) -> None:
        async with self._lock:
            conns = list(self._connections.get(session_id, []))

        dead = []

        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception as exc:
                logger.warning("WS SEND gagal (dibuang dari pool) | session=%s | %s", session_id, exc)
                dead.append(ws)

        if dead:
            async with self._lock:
                remaining = self._connections.get(session_id, [])
                self._connections[session_id] = [w for w in remaining if w not in dead]

    async def broadcast_tenant(self, tenant_id: str, payload: dict) -> None:
        """Broadcasts message exclusively to sessions belonging to the given tenant."""
        async with self._lock:
            target_sessions = [s_id for s_id, t_id in self._session_tenants.items() if t_id == tenant_id]

        for s_id in target_sessions:
            await self.send(s_id, payload)


manager = ConnectionManager()
