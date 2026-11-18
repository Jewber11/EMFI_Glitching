"""WebSocket telemetry endpoint."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    """Stream live telemetry to the client.

    On connect: send full state snapshot.
    Then: stream events from the Broadcaster queue.
    Client can send ``subscribe`` to filter topics, or ``ping``.
    """
    from control.deps import AppContext

    ctx: AppContext = socket.app.state.ctx
    client = f"{socket.client.host}:{socket.client.port}" if socket.client else "unknown"
    LOGGER.info("WS connect from %s", client)

    await socket.accept()
    q = ctx.broadcaster.register()
    subscribed: Optional[Set[str]] = None

    async def sender() -> None:
        try:
            while True:
                msg = await q.get()
                if subscribed is not None:
                    topic = msg.get("topic")
                    if topic and topic not in subscribed:
                        continue
                await socket.send_json(msg)
        except Exception:
            pass

    send_task = asyncio.create_task(sender())

    try:
        await socket.send_json({
            "type": "event",
            "topic": "state",
            "payload": ctx.state.snapshot(),
        })

        while True:
            msg = await socket.receive_json()
            action = msg.get("action")
            msg_id = msg.get("id")

            if action == "ping":
                await socket.send_json({"type": "ok", "id": msg_id})
            elif action == "subscribe":
                topics = msg.get("topics")
                if isinstance(topics, list):
                    subscribed = set(topics)
                    LOGGER.debug("WS %s subscribed to %s", client, subscribed)
                await socket.send_json({"type": "ok", "id": msg_id})
            else:
                await socket.send_json({
                    "type": "error",
                    "id": msg_id,
                    "error": f"unknown action: {action}",
                })
    except WebSocketDisconnect:
        LOGGER.info("WS disconnect from %s", client)
    finally:
        send_task.cancel()
        ctx.broadcaster.unregister(q)
