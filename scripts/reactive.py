"""Reactive session architecture — console prototype.

Framework-agnostic reactive state machine that observes events,
evaluates policies, and acts on session/agents via native mechanisms.

Two async processes:
  - Reactor: event-driven, consumes from queue, dispatches policies.
  - Ticker: time-driven, emits TICK events at fixed interval.

Both operate on shared ReactiveState. Policies read state + event,
produce Decisions. ReactiveSession executes Decisions via SessionHandle.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import Any, Protocol, Sequence, runtime_checkable


##### ENUMS #####


class EventKind(StrEnum):
    """Observable events in the reactive system."""

    USER_SPEAKING = auto()
    USER_SILENT = auto()
    USER_AWAY = auto()
    AGENT_SPEAKING = auto()
    AGENT_IDLE = auto()
    AGENT_THINKING = auto()
    TASK_COMPLETED = auto()
    TASK_FAILED = auto()
    TICK = auto()


class Action(StrEnum):
    """Executable actions on session/agent."""

    INTERRUPT = auto()
    REPLY = auto()
    SAY = auto()
    UPDATE_INSTRUCTIONS = auto()
    SWAP_AGENT = auto()


##### DATA #####


@dataclass(frozen=True, slots=True)
class Event:
    """Immutable event flowing through the reactor."""

    kind: EventKind
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)


@dataclass(frozen=True, slots=True)
class Decision:
    """Action specification produced by a policy."""

    action: Action
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReactiveState:
    """Shared mutable state — lives in session.userdata."""

    agent_state: str = "idle"
    user_state: str = "listening"
    turn_count: int = 0
    last_user_activity: float = field(default_factory=time.monotonic)
    data: dict[str, Any] = field(default_factory=dict)


##### PROTOCOLS #####


@runtime_checkable
class SessionHandle(Protocol):
    """Framework-agnostic session operations.

    Each agent framework implements this to bridge native APIs.
    LiveKit: wraps AgentSession. Console: prints actions.
    """

    async def interrupt(self) -> None: ...
    async def say(self, *, text: str) -> None: ...
    async def generate_reply(self, *, instructions: str) -> None: ...
    async def update_instructions(self, *, instructions: str) -> None: ...
    async def swap_agent(self, *, agent_id: str) -> None: ...


class Policy(Protocol):
    """Rule: state + event → decisions (empty tuple = no action)."""

    def evaluate(self, state: ReactiveState, event: Event) -> tuple[Decision, ...]: ...


##### CONSOLE SESSION #####


class ConsoleSession:
    """SessionHandle for console testing — prints executed actions."""

    @staticmethod
    def _log(msg: str) -> None:
        print(f"  [ACTION ] {msg}")

    async def interrupt(self) -> None:
        self._log("interrupt()")

    async def say(self, *, text: str) -> None:
        self._log(f"say({text!r})")

    async def generate_reply(self, *, instructions: str) -> None:
        self._log(f"generate_reply(instructions={instructions!r})")

    async def update_instructions(self, *, instructions: str) -> None:
        self._log(f"update_instructions({instructions!r})")

    async def swap_agent(self, *, agent_id: str) -> None:
        self._log(f"swap_agent({agent_id!r})")


##### REACTIVE SESSION #####


class ReactiveSession:
    """Async state machine: observe events, evaluate policies, act on session."""

    def __init__(
        self,
        session: SessionHandle,
        state: ReactiveState,
        policies: Sequence[Policy],
        *,
        tick_interval: float = 1.0,
    ) -> None:
        self._session = session
        self._state = state
        self._policies = tuple(policies)
        self._tick_interval = tick_interval
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._stop_event: asyncio.Event | None = None

    @property
    def state(self) -> ReactiveState:
        """Current reactive state (read-only access)."""
        return self._state

    def emit(self, event: Event) -> None:
        """Push event into reactor queue."""
        self._queue.put_nowait(event)

    async def run(self) -> None:
        """Start reactor + ticker. Blocks until stop()."""
        self._running = True
        self._stop_event = asyncio.Event()
        self._rs_log("SYSTEM", f"started (tick={self._tick_interval}s, policies={len(self._policies)})")
        self._rs_log("STATE", self._rs_format_state())

        reactor = asyncio.create_task(self._rs_reactor_loop())
        ticker = asyncio.create_task(self._rs_ticker_loop())

        await self._stop_event.wait()

        reactor.cancel()
        ticker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(reactor, ticker)

        self._rs_log("SYSTEM", "stopped")

    def stop(self) -> None:
        """Signal shutdown."""
        self._running = False
        if self._stop_event is not None:
            self._stop_event.set()

    # ── Private: loops ──

    async def _rs_reactor_loop(self) -> None:
        """Consume events from queue, dispatch policies."""
        while self._running:
            event = await self._queue.get()
            if not self._running:
                break
            await self._rs_dispatch(event)

    async def _rs_ticker_loop(self) -> None:
        """Emit TICK events at fixed interval."""
        while self._running:
            await asyncio.sleep(self._tick_interval)
            if self._running:
                self.emit(Event(kind=EventKind.TICK))

    # ── Private: dispatch ──

    async def _rs_dispatch(self, event: Event) -> None:
        """Apply event → update state → evaluate policies → act."""
        self._rs_apply(event)
        is_tick = event.kind == EventKind.TICK

        if not is_tick:
            payload_str = f" {event.payload}" if event.payload else ""
            self._rs_log("EVENT", f"{event.kind.value}{payload_str}")
            self._rs_log("STATE", self._rs_format_state())

        for policy in self._policies:
            decisions = policy.evaluate(self._state, event)
            if not decisions:
                continue
            name = type(policy).__name__
            if is_tick:
                self._rs_log("TICK", f"{name} triggered")
            self._rs_log("POLICY", f"{name} -> {len(decisions)} decision(s)")
            for decision in decisions:
                await self._rs_act(decision)

    def _rs_apply(self, event: Event) -> None:
        """Update state from event (observation step)."""
        match event.kind:
            case EventKind.USER_SPEAKING:
                self._state.user_state = "speaking"
                self._state.last_user_activity = event.timestamp
            case EventKind.USER_SILENT:
                if self._state.user_state == "speaking":
                    self._state.turn_count += 1
                self._state.user_state = "listening"
                self._state.last_user_activity = event.timestamp
            case EventKind.USER_AWAY:
                self._state.user_state = "away"
            case EventKind.AGENT_SPEAKING:
                self._state.agent_state = "speaking"
            case EventKind.AGENT_IDLE:
                self._state.agent_state = "idle"
            case EventKind.AGENT_THINKING:
                self._state.agent_state = "thinking"
            case EventKind.TASK_COMPLETED | EventKind.TASK_FAILED:
                self._state.data.update(event.payload)

    async def _rs_act(self, decision: Decision) -> None:
        """Execute a decision via session handle."""
        p = decision.payload
        match decision.action:
            case Action.INTERRUPT:
                await self._session.interrupt()
            case Action.REPLY:
                await self._session.generate_reply(instructions=p.get("instructions", ""))
            case Action.SAY:
                await self._session.say(text=p.get("text", ""))
            case Action.UPDATE_INSTRUCTIONS:
                await self._session.update_instructions(instructions=p.get("instructions", ""))
            case Action.SWAP_AGENT:
                await self._session.swap_agent(agent_id=p.get("agent_id", ""))

    # ── Private: formatting ──

    def _rs_format_state(self) -> str:
        """Format state for log output."""
        s = self._state
        parts = [f"user={s.user_state}", f"agent={s.agent_state}", f"turns={s.turn_count}"]
        if s.data:
            parts.append(f"data={s.data}")
        return " ".join(parts)

    @staticmethod
    def _rs_log(tag: str, msg: str) -> None:
        print(f"  [{tag:<8}] {msg}")


##### EXAMPLE POLICIES #####


class AwayPolicy:
    """If user silent too long on TICK, prompt them."""

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout
        self._notified = False

    def evaluate(self, state: ReactiveState, event: Event) -> tuple[Decision, ...]:
        if event.kind == EventKind.USER_SPEAKING:
            self._notified = False
            return ()

        if event.kind != EventKind.TICK:
            return ()

        elapsed = event.timestamp - state.last_user_activity
        if elapsed > self._timeout and not self._notified:
            self._notified = True
            return (Decision(action=Action.SAY, payload={"text": "Are you still there?"}),)

        return ()


class TaskCompletedPolicy:
    """On task completion/failure, interrupt and share results."""

    def evaluate(self, state: ReactiveState, event: Event) -> tuple[Decision, ...]:
        match event.kind:
            case EventKind.TASK_COMPLETED:
                msg = event.payload.get("message", "Task completed.")
                return (
                    Decision(action=Action.INTERRUPT),
                    Decision(
                        action=Action.REPLY,
                        payload={"instructions": f"Share this result with the user: {msg}"},
                    ),
                )
            case EventKind.TASK_FAILED:
                error = event.payload.get("error", "Unknown error.")
                return (
                    Decision(
                        action=Action.REPLY,
                        payload={"instructions": f"A background task failed: {error}. Inform the user."},
                    ),
                )
            case _:
                return ()


class TurnEscalationPolicy:
    """After N turns without resolution, swap to a more capable agent."""

    def __init__(self, threshold: int = 5, target_agent: str = "escalation") -> None:
        self._threshold = threshold
        self._target = target_agent
        self._escalated = False

    def evaluate(self, state: ReactiveState, event: Event) -> tuple[Decision, ...]:
        if self._escalated or event.kind != EventKind.USER_SILENT:
            return ()

        if state.turn_count >= self._threshold:
            self._escalated = True
            return (
                Decision(
                    action=Action.UPDATE_INSTRUCTIONS,
                    payload={"instructions": "The conversation is taking too long. Wrap up or escalate."},
                ),
                Decision(action=Action.SWAP_AGENT, payload={"agent_id": self._target}),
            )

        return ()


##### CONSOLE RUNNER #####


_HELP: dict[str, str] = {
    "speak": "User starts speaking",
    "silent": "User stops speaking (increments turn)",
    "away": "User goes away",
    "done <msg>": "Background task completed",
    "fail <msg>": "Background task failed",
    "set <k> <v>": "Set state.data[key] = value",
    "state": "Print current state",
    "help": "Show commands",
    "quit": "Exit",
}


def _parse_input(line: str) -> Event | str | None:
    """Parse console input into Event, command string, or None."""
    parts = line.strip().split(maxsplit=1)
    if not parts:
        return None

    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    match cmd:
        case "speak":
            return Event(kind=EventKind.USER_SPEAKING)
        case "silent":
            return Event(kind=EventKind.USER_SILENT)
        case "away":
            return Event(kind=EventKind.USER_AWAY)
        case "done":
            return Event(kind=EventKind.TASK_COMPLETED, payload={"message": arg or "done"})
        case "fail":
            return Event(kind=EventKind.TASK_FAILED, payload={"error": arg or "unknown"})
        case "state" | "help" | "quit":
            return cmd
        case "set":
            return f"set:{arg}"
        case _:
            return None


async def run_console(*, tick_interval: float = 2.0, away_timeout: float = 10.0) -> None:
    """Interactive console for testing the reactive session."""
    state = ReactiveState()
    session = ConsoleSession()
    policies: tuple[Policy, ...] = (
        AwayPolicy(timeout=away_timeout),
        TaskCompletedPolicy(),
        TurnEscalationPolicy(threshold=5),
    )

    reactive = ReactiveSession(
        session=session,
        state=state,
        policies=policies,
        tick_interval=tick_interval,
    )

    task = asyncio.create_task(reactive.run())

    print("\n  ReactiveSession Console — type 'help' for commands\n")

    try:
        while True:
            line = await asyncio.to_thread(input, "> ")
            result = _parse_input(line)

            match result:
                case Event() as event:
                    reactive.emit(event)
                    await asyncio.sleep(0.05)

                case "state":
                    s = reactive.state
                    print(f"  user={s.user_state} agent={s.agent_state} turns={s.turn_count}")
                    print(f"  last_activity={s.last_user_activity:.1f}")
                    print(f"  data={s.data}")

                case "help":
                    for cmd, desc in _HELP.items():
                        print(f"  {cmd:<16} {desc}")

                case "quit":
                    break

                case str(s) if s.startswith("set:"):
                    kv = s[4:].split(maxsplit=1)
                    if len(kv) == 2:
                        reactive.state.data[kv[0]] = kv[1]
                        print(f"  state.data[{kv[0]!r}] = {kv[1]!r}")
                    else:
                        print("  Usage: set <key> <value>")

                case _:
                    print("  Unknown command. Type 'help'.")

    except (EOFError, KeyboardInterrupt):
        print()

    finally:
        reactive.stop()
        await task


if __name__ == "__main__":
    asyncio.run(run_console())
