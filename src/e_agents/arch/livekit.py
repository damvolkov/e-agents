"""LiveKit implementation of ReactiveOps.

Bridges the framework-agnostic reactive system with LiveKit Agents SDK.
All concrete agents inherit from LiveKitReactiveAgent.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import orjson as json
from livekit.agents import Agent

from e_agents.arch.models import Event, EventEffect, TaskStatus
from e_agents.arch.ops import ReactiveOps
from e_agents.arch.state import ReactiveState

logger = logging.getLogger("rtc.base")

_DELIVERY_TIMEOUT = 30.0


def truncate_thread(
    items: list,
    keep_last_n: int = 6,
    *,
    keep_system: bool = False,
    keep_fn_calls: bool = False,
) -> list:
    """Keep last N relevant messages from LiveKit's chat context. O(n)."""
    def _keep(item) -> bool:
        match (item.type, getattr(item, "role", None)):
            case ("message", "system") if not keep_system:
                return False
            case (("function_call" | "function_call_output"), _) if not keep_fn_calls:
                return False
            case _:
                return True

    kept: list = []
    for item in reversed(items):
        if _keep(item):
            kept.append(item)
        if len(kept) >= keep_last_n:
            break
    kept.reverse()

    while kept and kept[0].type in ("function_call", "function_call_output"):
        kept.pop(0)
    return kept


class LiveKitReactiveAgent(Agent, ReactiveOps):
    """LiveKit Agent with double-loop reactive capabilities."""

    def __init__(
        self,
        *,
        instructions: str,
        keep_last_n: int = 6,
        monitor_interval: float = 0.5,
        **kwargs: Any,
    ) -> None:
        Agent.__init__(self, instructions=instructions, **kwargs)
        ReactiveOps.__init__(self, monitor_interval=monitor_interval)
        self._keep_last_n = keep_last_n
        self._generation_lock = asyncio.Lock()

    # ── ReactiveOps contract (verb_entity) ───────────────────────────────

    def get_state(self) -> ReactiveState:
        return self.session.userdata

    async def push_thread(self, payload: dict[str, Any]) -> None:
        ctx = self.chat_ctx.copy()
        ctx.add_message(
            role="system",
            content=f"[background_data] {json.dumps(payload).decode()}",
        )
        await self.update_chat_ctx(ctx)

    async def switch_agent(self, target_name: str) -> None:
        """Store target in state; the calling tool reads and returns it."""
        state = self.get_state()
        await state.set("_pending_handoff", target_name)
        logger.info("🔀 SWITCH_AGENT target=%s", target_name)

    async def deliver_event(self, event: Event, effect: EventEffect) -> None:
        """Deliver event via LiveKit: interrupt → push → generate_reply."""
        match effect:
            case EventEffect.INTERRUPT:
                async with self._generation_lock:
                    await self.push_thread(event.payload)
                    await self.session.interrupt()
                    msg = self.format_event(event)
                    instructions = msg or "New information has been added to your context. Share it with the user now."
                    handle = self.session.generate_reply(
                        instructions=instructions,
                        tool_choice="none",
                    )
                    try:
                        await asyncio.wait_for(
                            handle.wait_for_playout(), timeout=_DELIVERY_TIMEOUT,
                        )
                    except TimeoutError:
                        logger.warning("⚠️ DELIVERY_TIMEOUT event=%s", event.source)
            case EventEffect.ENRICH:
                await self.push_thread(event.payload)

    def format_event(self, event: Event) -> str | None:
        match event.status:
            case TaskStatus.COMPLETED:
                return event.payload.get("message")
            case TaskStatus.FAILED:
                return f"Ha ocurrido un error: {event.payload.get('error', 'desconocido')}"
            case _:
                return None

    # ── LiveKit lifecycle hooks ──────────────────────────────────────────

    async def on_enter(self) -> None:
        state = self.get_state()
        state.thread = self.chat_ctx
        await self.reactive_start()

    async def on_exit(self) -> None:
        await self.reactive_stop()

    async def on_reactive_ready(self) -> None:
        self.session.generate_reply()

    async def on_user_turn_completed(
        self, turn_ctx: Any, new_message: Any = None,
    ) -> None:
        """Inject accumulated TURN_BOUNDARY events into this turn's context."""
        for event, effect in self.drain_turn_events():
            match effect:
                case EventEffect.INTERRUPT | EventEffect.ENRICH:
                    msg = self.format_event(event)
                    content = msg if msg else json.dumps(event.payload).decode()
                    turn_ctx.add_message(
                        role="system",
                        content=f"[background_data] {content}",
                    )

    # ── Agent transfer (LiveKit-specific) ────────────────────────────────

    async def _on_agent_transfer(self, prev_name: str) -> None:
        """Merge relevant history from the previous agent's chat context."""
        state = self.get_state()
        prev = state.prev
        if prev is None or not hasattr(prev, "chat_ctx"):
            return

        ctx = self.chat_ctx.copy()
        prev_items = truncate_thread(
            prev.chat_ctx.items,
            keep_last_n=self._keep_last_n,
            keep_fn_calls=True,
        )
        existing_ids = {item.id for item in ctx.items}
        ctx.items.extend(i for i in prev_items if i.id not in existing_ids)
        ctx.add_message(
            role="system",
            content=f"Context transferred from {prev_name}. You are now {type(self).__name__}.",
        )
        await self.update_chat_ctx(ctx)

    async def transfer_to(self, name: str) -> Agent:
        """Use inside @function_tool to execute a transfer."""
        state = self.get_state()
        state.set_current(name)
        return state.get_agent(name)
