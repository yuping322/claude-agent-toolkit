#!/usr/bin/env python3
# observability.py - Event bus & standard events

from __future__ import annotations
import time
import threading
from typing import Callable, Dict, List, Type, Optional, Any
from pydantic import BaseModel, Field

# --- Base Event ---------------------------------------------------
class BaseEvent(BaseModel):
    ts: float = Field(default_factory=lambda: time.time())
    event_type: str
    component: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)

# --- Specific Events ----------------------------------------------
class LogEvent(BaseEvent):
    level: str
    message: str

class ModelInvocationEvent(BaseEvent):
    provider: str
    tokens_input: int
    tokens_output: int
    latency_ms: float
    cost_usd: float

class ModelUsageEvent(BaseEvent):
    provider: str
    requests_total: int
    tokens_in_total: int
    tokens_out_total: int
    cost_total_usd: float

class DependencyPoolEvent(BaseEvent):
    action: str  # acquire|release|cleanup
    dependency_type: str
    agent_id: Optional[str] = None
    in_use: int
    available: int

class SandboxExecutionEvent(BaseEvent):
    agent_id: str
    sandbox_strategy: str
    phase: str  # start|finish|error
    command: Optional[str] = None
    success: Optional[bool] = None
    latency_ms: Optional[float] = None

class StateSnapshot(BaseEvent):
    agent_id: str
    stage: str
    pending_tasks: int
    recent_message: Optional[str] = None

# --- Event Bus ----------------------------------------------------
class EventBus:
    def __init__(self, buffer_size: int = 10000):
        self._subs: Dict[str, List[Callable[[BaseEvent], None]]] = {}
        self._buffer: List[BaseEvent] = []
        self._buffer_size = buffer_size
        self._lock = threading.Lock()

    def publish(self, event: BaseEvent) -> None:
        etype = event.event_type
        with self._lock:
            if len(self._buffer) >= self._buffer_size:
                # drop oldest
                self._buffer.pop(0)
            self._buffer.append(event)
        # dispatch
        for fn in self._subs.get(etype, []):
            try:
                fn(event)
            except Exception:
                # swallow subscriber errors
                pass

    def subscribe(self, event_type: str, handler: Callable[[BaseEvent], None]) -> None:
        self._subs.setdefault(event_type, []).append(handler)

    def recent(self, limit: int = 100) -> List[BaseEvent]:
        with self._lock:
            return list(self._buffer[-limit:])

# global instance
_event_bus = EventBus()

def get_event_bus() -> EventBus:
    return _event_bus

# convenient export
event_bus = get_event_bus()

__all__ = [
    "BaseEvent","LogEvent","ModelInvocationEvent","ModelUsageEvent","DependencyPoolEvent",
    "SandboxExecutionEvent","StateSnapshot","EventBus","event_bus","get_event_bus"
]
