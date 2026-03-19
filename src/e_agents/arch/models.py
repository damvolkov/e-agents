"""Reactive agent architecture — pure data models.

No async. No framework deps. Just types, enums, and frozen Pydantic models.

── Naming Convention ──────────────────────────────────────────────────────────
Entities:  Event, Task, Agent, State, Thread, User
Qualifier: Config (definitions), Entry (registry), Policy (rules)
Enums:     Entity + semantic qualifier (TaskStatus, EventStrategy, EventEffect)
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import time
from enum import IntEnum, StrEnum, auto
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field


# ─── Shared Enums ────────────────────────────────────────────────────────────

class Priority(IntEnum):
    """Task/event urgency — lower value = higher urgency."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


# ─── Task Enums ──────────────────────────────────────────────────────────────

class TaskStatus(StrEnum):
    """Lifecycle state of a background task."""
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


# ─── Event Enums ─────────────────────────────────────────────────────────────

class EventStrategy(StrEnum):
    """WHEN the outer agent reacts to an event."""
    IMMEDIATE = "immediate"
    TURN_BOUNDARY = "turn_boundary"
    NATURAL_PAUSE = "natural_pause"
    ENQUEUE = "enqueue"


class EventEffect(StrEnum):
    """WHAT the outer agent does with an event."""
    INTERRUPT = "interrupt"
    ENRICH = "enrich"
    HANDOFF = "handoff"
    NOOP = "noop"


# ─── Event Policy ────────────────────────────────────────────────────────────

class EventPolicy(BaseModel):
    """Configurable mapping: Priority → (strategy, effect). O(1) resolve."""
    model_config = ConfigDict(frozen=True)

    rules: dict[Priority, tuple[EventStrategy, EventEffect]] = Field(
        default_factory=lambda: {
            Priority.CRITICAL: (EventStrategy.IMMEDIATE, EventEffect.INTERRUPT),
            Priority.HIGH: (EventStrategy.TURN_BOUNDARY, EventEffect.INTERRUPT),
            Priority.NORMAL: (EventStrategy.TURN_BOUNDARY, EventEffect.ENRICH),
            Priority.LOW: (EventStrategy.NATURAL_PAUSE, EventEffect.ENRICH),
            Priority.BACKGROUND: (EventStrategy.ENQUEUE, EventEffect.NOOP),
        },
    )
    idle_timeout_seconds: float = 3.0

    def resolve(self, priority: Priority) -> tuple[EventStrategy, EventEffect]:
        return self.rules.get(
            priority,
            (EventStrategy.ENQUEUE, EventEffect.NOOP),
        )


# ─── Event ───────────────────────────────────────────────────────────────────

class Event(BaseModel):
    """Structured payload pushed by inner agents/tools into the reactive queue."""
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    task_id: str
    source: str
    priority: Priority = Priority.NORMAL
    status: TaskStatus = TaskStatus.COMPLETED
    effect: EventEffect = EventEffect.ENRICH
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.monotonic)

    @computed_field
    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.created_at


# ─── Task Config ─────────────────────────────────────────────────────────────

class TaskConfig(BaseModel):
    """Definition of a background task to submit to the orchestrator."""
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str
    priority: Priority = Priority.NORMAL
    effect: EventEffect = EventEffect.ENRICH
    source: str = "system"
    meta: dict[str, Any] = Field(default_factory=dict)


# ─── Agent Entry ─────────────────────────────────────────────────────────────

class AgentEntry(BaseModel):
    """Registry record for an agent in the reactive system."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    ref: Any
    role: str = "inner"
    active: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)