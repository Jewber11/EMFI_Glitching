"""WebSocket event envelope shared by Control and Develop."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class WsTopic(str, Enum):
    """Canonical set of WS topics.

    Control publishes: POSITION, ARM, COUNTER, ATTEMPT, DEVICE_STATUS,
    CAMPAIGN_PROGRESS, ERROR.

    Develop publishes: BUILD_LOG, BUILD_STATUS, AGENT_OUTPUT.
    """

    # Control
    POSITION = "position"
    ARM = "arm"
    COUNTER = "counter"
    ATTEMPT = "attempt"
    DEVICE_STATUS = "device_status"
    CAMPAIGN_PROGRESS = "campaign_progress"
    ERROR = "error"
    STATE = "state"

    # Develop
    BUILD_LOG = "build_log"
    BUILD_STATUS = "build_status"
    AGENT_OUTPUT = "agent_output"


class WsEvent(BaseModel):
    """Envelope every server → client WS message uses."""

    type: str = Field("event", description="event | ok | error")
    topic: Optional[WsTopic] = None
    payload: Optional[Dict[str, Any]] = None
    id: Optional[str] = Field(None, description="Echoed for request/response correlation")
    error: Optional[str] = None
