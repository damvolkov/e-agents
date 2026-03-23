"""Reactive session architecture — reusable policies.

Policies are sync (fast evaluation, no I/O). They return zero or more Decisions.
Policies may have private state (e.g., _notified flag in AwayPolicy).

Taxonomy (N1):
  Entities:  AwayPolicy, TaskCompletedPolicy, TurnEscalationPolicy
  Verb:      evaluate (the single method on Policy protocol)
"""

from __future__ import annotations

from e_agents.arch.models import Action, Decision, Event, EventKind, ReactiveState


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
            return (Decision(action=Action.SAY, payload={"text": "¿Sigues ahí?"}),)
        return ()


class TaskCompletedPolicy:
    """On task completion/failure, interrupt and share results."""

    def evaluate(self, state: ReactiveState, event: Event) -> tuple[Decision, ...]:
        match event.kind:
            case EventKind.TASK_COMPLETED:
                msg = event.payload.get("message", "Tarea completada.")
                return (
                    Decision(action=Action.INTERRUPT),
                    Decision(
                        action=Action.REPLY,
                        payload={
                            "instructions": (
                                "Comparte este resultado con el usuario de forma "
                                f"natural: {msg}"
                            ),
                        },
                    ),
                )
            case EventKind.TASK_FAILED:
                error = event.payload.get("error", "Error desconocido.")
                return (
                    Decision(
                        action=Action.REPLY,
                        payload={
                            "instructions": (
                                f"Una tarea en segundo plano falló: {error}. "
                                "Informa al usuario."
                            ),
                        },
                    ),
                )
            case _:
                return ()


class TurnEscalationPolicy:
    """After N turns without resolution, escalate."""

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
                    payload={"instructions": "La conversación está tardando. Cierra o escala."},
                ),
                Decision(action=Action.SWAP_AGENT, payload={"agent_id": self._target}),
            )
        return ()
