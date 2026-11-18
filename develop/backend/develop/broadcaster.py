"""In-memory async pub/sub for WebSocket event broadcasting."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Dict, Set

from fastapi import WebSocket

from emfi_protocol.ws_events import WsEvent, WsTopic

log = logging.getLogger(__name__)


class Broadcaster:
    def __init__(self) -> None:
        self._subscribers: Dict[WsTopic, Set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, ws: WebSocket, topic: WsTopic) -> None:
        async with self._lock:
            self._subscribers[topic].add(ws)
        log.debug("Client subscribed to %s (%d total)", topic.value, len(self._subscribers[topic]))

    async def unsubscribe_all(self, ws: WebSocket) -> None:
        async with self._lock:
            for topic_set in self._subscribers.values():
                topic_set.discard(ws)

    async def broadcast(self, topic: WsTopic, payload: dict) -> None:
        event = WsEvent(type="event", topic=topic, payload=payload)
        msg = event.model_dump(mode="json")
        async with self._lock:
            dead: list[WebSocket] = []
            for ws in self._subscribers.get(topic, set()):
                try:
                    await ws.send_json(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._subscribers[topic].discard(ws)
                log.debug("Removed dead client from %s", topic.value)


broadcaster = Broadcaster()
