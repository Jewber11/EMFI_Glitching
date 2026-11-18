"""WebSocket for build-log + agent-output streaming."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from emfi_protocol.ws_events import WsTopic

from develop.broadcaster import broadcaster

log = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])

TOPIC_MAP = {t.value: t for t in WsTopic}


@router.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    """Accept WS connections. Clients send subscribe/unsubscribe messages:

        {"type": "subscribe", "topic": "build_log"}
        {"type": "unsubscribe", "topic": "build_log"}

    The broadcaster pushes events to subscribed clients.
    """
    client = f"{socket.client.host}:{socket.client.port}" if socket.client else "unknown"
    log.info("WS connect from %s", client)
    await socket.accept()
    try:
        await socket.send_json({"type": "ok", "detail": "connected"})
        while True:
            msg = await socket.receive_json()
            msg_type = msg.get("type", "")
            topic_str = msg.get("topic", "")
            topic = TOPIC_MAP.get(topic_str)

            if msg_type == "subscribe" and topic:
                await broadcaster.subscribe(socket, topic)
                await socket.send_json({"type": "ok", "detail": f"subscribed to {topic_str}"})
            elif msg_type == "unsubscribe" and topic:
                await broadcaster.unsubscribe_all(socket)
                await socket.send_json({"type": "ok", "detail": f"unsubscribed from {topic_str}"})
            else:
                await socket.send_json({
                    "type": "error",
                    "id": msg.get("id"),
                    "error": f"Unknown message type {msg_type!r} or topic {topic_str!r}",
                })
    except WebSocketDisconnect:
        log.info("WS disconnect from %s", client)
    finally:
        await broadcaster.unsubscribe_all(socket)
