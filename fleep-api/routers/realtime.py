"""
WebSocket endpoint that pushes live transaction status updates to fleep-ui.

Connections are grouped per-user via a small in-process ConnectionManager.
For a single-instance deployment this is sufficient; a multi-instance
deployment would back this with a Redis pub/sub channel (the `broadcast`
call is already isolated so that swap is a single-file change).
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("fleep.realtime")
router = APIRouter(tags=["realtime"])


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: Dict[uuid.UUID, Set[WebSocket]] = {}

    async def connect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(user_id, set()).add(websocket)
        logger.info("ws connected user=%s total=%d", user_id, len(self._connections[user_id]))

    def disconnect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        sockets = self._connections.get(user_id)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: uuid.UUID, message: dict) -> None:
        sockets = self._connections.get(user_id, set())
        stale: Set[WebSocket] = set()
        for ws in sockets:
            try:
                await ws.send_text(json.dumps(message, default=str))
            except Exception:  # noqa: BLE001
                stale.add(ws)
        for ws in stale:
            sockets.discard(ws)


manager = ConnectionManager()


@router.websocket("/ws/transactions/{user_id}")
async def transaction_stream(websocket: WebSocket, user_id: uuid.UUID) -> None:
    # NOTE: token-based auth for WS connections is handled at the ASGI
    # middleware layer (query-param token -> user_id resolution) in
    # production; omitted here to keep this module focused on the
    # connection-management logic itself.
    await manager.connect(user_id, websocket)
    try:
        while True:
            # We don't expect inbound messages on this channel today, but
            # reading keeps the connection alive and lets us detect
            # disconnects promptly instead of waiting for a TCP timeout.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)


async def notify_transaction_update(user_id: uuid.UUID, transaction_id: uuid.UUID, status: str) -> None:
    """Called by the transaction engine (or a router) after a successful
    transition so the UI updates without polling."""
    await manager.send_to_user(
        user_id,
        {"type": "transaction.status_changed", "transaction_id": str(transaction_id), "status": status},
    )
