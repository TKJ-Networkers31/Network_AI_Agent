"""
api/ws_manager.py — registry koneksi WebSocket AIRA, dikelompokkan per
session_id (sama seperti sesi chat REST). Terpisah dari api/state.py
supaya tidak mencampur cache ConversationMemory dengan koneksi socket.
"""

import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger("aira.ws")


class ConnectionManager:

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(session_id, []).append(websocket)
        logger.info("WS CONNECT | session=%s | total_conn=%d", session_id, len(self._connections.get(session_id, [])))

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(session_id, [])
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                self._connections.pop(session_id, None)
        logger.info("WS DISCONNECT | session=%s", session_id)

    async def send(self, session_id: str, payload: dict) -> None:
        """
        Kirim ke semua koneksi aktif untuk session_id ini (biasanya
        cuma satu tab, tapi mendukung multi-tab/multi-device tanpa
        perubahan tambahan).
        """
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


manager = ConnectionManager()