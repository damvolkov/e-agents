"""Reactive agent architecture — ops mixin.

Provides the double-loop reactive engine. Mix into any framework's agent base:

    class MyAgent(FrameworkAgent, ReactiveOps):
        ...

── Naming Convention ──────────────────────────────────────────────────────────
Verbs:     get, set, push, switch, format, submit, cancel, drain, deliver
Entities:  state, event, task, agent, thread, user

Abstract methods follow verb_entity pattern:
  get_state, push_thread, switch_agent, deliver_event, format_event
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import abstractmethod
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from e_agents.arch.models import (
    Event,
    EventEffect,
    EventStrategy,
    TaskConfig,
)
from e_agents.arch.state import ReactiveState

logger = logging.getLogger("reactive.ops")


class ReactiveOps:
    """Mixin providing double-loop reactive capabilities.

    ── Data Flow ──────────────────────────────────────────────────────────────
    Inner agents/tools → state.push_event(event) → queue → monitor →
      IMMEDIATE      → deliver_event()     (interrupt + push + generate)
      TURN_BOUNDARY  → _pending_turn       (injected at next user turn)
      NATURAL_PAUSE  → _pending_idle       (flushed during idle)
      ENQUEUE        → _pending_idle       (flushed during idle)
    ────────────────────────────────────────────────────────────────────────────
    """

    def __init__(self, *, monitor_interval: float = 0.5, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._monitor_interval = monitor_interval
        self._monitor_handle: asyncio.Task[None] | None = None
        self._pending_turn: list[tuple[Event, EventEffect]] = []
        self._pending_idle: list[tuple[Event, EventEffect]] = []
        self._idle_since: float = time.monotonic()

    # ═════════════════════════════════════════════════════════════════════════
    #  ABSTRACT — framework must implement (verb_entity pattern)
    # ═════════════════════════════════════════════════════════════════════════

    @abstractmethod
    def get_state(self) -> ReactiveState:
        """Return the ReactiveState from the framework's session."""

    @abstractmethod
    async def push_thread(self, payload: dict[str, Any]) -> None:
        """Push background data into the conversation thread silently."""

    @abstractmethod
    async def switch_agent(self, target_name: str) -> None:
        """Execute an agent transfer through the framework's mechanism."""

    @abstractmethod
    async def deliver_event(self, event: Event, effect: EventEffect) -> None:
        """Deliver an event to the user through the framework's native mechanism.

        INTERRUPT: interrupt current speech → enrich thread → generate reply.
        ENRICH:    enrich thread silently (LLM sees on next turn).
        """

    @abstractmethod
    def format_event(self, event: Event) -> str | None:
        """Format an Event for user delivery. Return None to skip."""

    # ═════════════════════════════════════════════════════════════════════════
    #  OPTIONAL OVERRIDE
    # ═════════════════════════════════════════════════════════════════════════

    async def on_reactive_ready(self) -> None:
        """Called after reactive_start() completes. Override for initial reply."""

    # ═════════════════════════════════════════════════════════════════════════
    #  LIFECYCLE — call from framework hooks
    # ═════════════════════════════════════════════════════════════════════════

    async def reactive_start(self) -> None:
        """Start the reactive monitor. Call from framework's on_enter hook."""
        state = self.get_state()
        agent_name = type(self).__name__

        state.set_current(agent_name)

        if state.prev_name:
            await self._on_agent_transfer(state.prev_name)

        self._start_monitor()
        self._idle_since = time.monotonic()

        logger.info("🔄 REACTIVE_START agent=%s prev=%s", agent_name, state.prev_name)
        await self.on_reactive_ready()

    async def reactive_stop(self) -> None:
        """Stop the reactive monitor. Call from framework's on_exit hook."""
        self._stop_monitor()
        logger.info("⏹️ REACTIVE_STOP agent=%s", type(self).__name__)

    async def _on_agent_transfer(self, prev_name: str) -> None:
        """Hook called when this agent was activated via transfer. Override in bridge."""

    # ═════════════════════════════════════════════════════════════════════════
    #  TURN BOUNDARY — called by framework's on_user_turn_completed
    # ═════════════════════════════════════════════════════════════════════════

    def drain_turn_events(self) -> list[tuple[Event, EventEffect]]:
        """Pop all TURN_BOUNDARY events. Called by framework bridge."""
        batch = sorted(self._pending_turn, key=lambda x: x[0].priority)
        self._pending_turn.clear()
        return batch

    # ═════════════════════════════════════════════════════════════════════════
    #  CONVENIENCE — for agent tools
    # ═════════════════════════════════════════════════════════════════════════

    async def submit_task(
        self,
        config: TaskConfig,
        handler: Callable[..., Awaitable[dict[str, Any]]],
        **kwargs: Any,
    ) -> str:
        """Submit a background task from within a tool."""
        return await self.get_state().submit_task(config, handler, **kwargs)

    async def push_event(self, event: Event) -> None:
        """Push an event directly (no background task)."""
        await self.get_state().push_event(event)

    # ═════════════════════════════════════════════════════════════════════════
    #  MONITOR ENGINE (private)
    # ═════════════════════════════════════════════════════════════════════════

    def _start_monitor(self) -> None:
        if self._monitor_handle is None or self._monitor_handle.done():
            self._monitor_handle = asyncio.create_task(self._monitor_loop())

    def _stop_monitor(self) -> None:
        if self._monitor_handle and not self._monitor_handle.done():
            self._monitor_handle.cancel()
            self._monitor_handle = None

    async def _monitor_loop(self) -> None:
        """Core reactive loop: wait → evaluate → act."""
        state = self.get_state()

        with suppress(asyncio.CancelledError):
            while True:
                if event := await state.wait_event(timeout=self._monitor_interval):
                    await self._evaluate_event(event, state)

                idle = time.monotonic() - self._idle_since
                if self._pending_idle and idle >= state.policy.idle_timeout_seconds:
                    await self._flush_idle()

    async def _evaluate_event(self, event: Event, state: ReactiveState) -> None:
        """Evaluate a single event against policy."""
        strategy, default_effect = state.policy.resolve(event.priority)
        effect = event.effect if event.effect != EventEffect.ENRICH else default_effect

        logger.info(
            "📨 EVALUATE src=%s pri=%s strat=%s eff=%s st=%s",
            event.source, event.priority.name, strategy, effect, event.status,
        )

        match strategy:
            case EventStrategy.IMMEDIATE:
                await self._apply_effect(event, effect)
            case EventStrategy.TURN_BOUNDARY:
                self._pending_turn.append((event, effect))
            case EventStrategy.NATURAL_PAUSE | EventStrategy.ENQUEUE:
                self._pending_idle.append((event, effect))

    async def _apply_effect(self, event: Event, effect: EventEffect) -> None:
        """Execute the resolved effect for an event."""
        match effect:
            case EventEffect.INTERRUPT:
                await self.deliver_event(event, effect)
            case EventEffect.ENRICH:
                await self.push_thread(event.payload)
            case EventEffect.HANDOFF:
                await self.switch_agent(event.payload.get("target", ""))
            case EventEffect.NOOP:
                pass
        self._idle_since = time.monotonic()

    async def _flush_idle(self) -> None:
        """Deliver all accumulated idle-pending events."""
        batch = sorted(self._pending_idle, key=lambda x: x[0].priority)
        self._pending_idle.clear()

        for event, effect in batch:
            await self._apply_effect(event, effect)


# ═════════════════════════════════════════════════════════════════════════════
#  IMPLEMENTATION CONTRACT
# ═════════════════════════════════════════════════════════════════════════════
#
# ┌──────────────────────────────────────────────────────────────────────────┐
# │  MUST IMPLEMENT (abstract)              verb_entity pattern             │
# ├──────────────────────┬───────────────────────────────────────────────────┤
# │  get_state()         │ Return ReactiveState from framework session      │
# │  push_thread()       │ Push payload into conversation thread silently   │
# │  switch_agent()      │ Execute agent transfer via framework mechanism   │
# │  deliver_event()     │ Deliver event: interrupt + push + generate       │
# │  format_event()      │ Event → user-facing string (or None to skip)     │
# ├──────────────────────┴───────────────────────────────────────────────────┤
# │  OPTIONAL OVERRIDE                                                       │
# ├──────────────────────┬───────────────────────────────────────────────────┤
# │  on_reactive_ready() │ Called after reactive_start() completes          │
# │  _on_agent_transfer()│ Called when activated via agent transfer         │
# ├──────────────────────┴───────────────────────────────────────────────────┤
# │  MUST CALL FROM FRAMEWORK HOOKS                                          │
# ├──────────────────────┬───────────────────────────────────────────────────┤
# │  reactive_start()    │ Call on agent enter / activate                    │
# │  reactive_stop()     │ Call on agent exit / deactivate (if hook exists)  │
# ├──────────────────────┴───────────────────────────────────────────────────┤
# │  FRAMEWORK BRIDGE CALLS                                                  │
# ├──────────────────────┬───────────────────────────────────────────────────┤
# │  drain_turn_events() │ Pop TURN_BOUNDARY events in on_user_turn hook    │
# ├──────────────────────┴───────────────────────────────────────────────────┤
# │  AVAILABLE TO TOOLS                     verb_entity pattern             │
# ├──────────────────────┬───────────────────────────────────────────────────┤
# │  submit_task()       │ Launch a background task (non-blocking)           │
# │  push_event()        │ Push an Event directly (no background task)       │
# │  get_state()         │ Access the full ReactiveState                     │
# └──────────────────────┴───────────────────────────────────────────────────┘
