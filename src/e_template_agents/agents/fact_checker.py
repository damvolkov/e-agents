"""Fact checker agent - Inner-loop specialist for claim verification."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from livekit.agents import Agent, RunContext, function_tool

from e_template_agents.tasks.status import TaskPriority, TaskStatus

if TYPE_CHECKING:
    from e_template_agents.models.agent import AgentConfig
    from e_template_agents.sessions.double_loop import DoubleLoopUserData
    from e_template_agents.tasks.executor import TaskExecutor


class FactCheckerAgent(Agent):
    """Inner-loop specialist for verifying claims and cross-referencing data."""

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(instructions=config.instructions)
        self._config = config

    @property
    def _userdata(self) -> DoubleLoopUserData:
        return self.session.userdata

    @property
    def _executor(self) -> TaskExecutor:
        return self._userdata.task_executor

    async def on_enter(self) -> None:
        """Handle activation."""
        pending = self._userdata.task_registry.get_pending_notifications()

        for notification in pending:
            if notification.task.initiated_by != self.id and not notification.acknowledged:
                self._userdata.task_registry.acknowledge_notification(notification.task.id)

        self.session.generate_reply(
            instructions=(
                "You are now in verification mode. Ask the user what claims or statements "
                "they want verified, or begin checking based on conversation context."
            )
        )

    @function_tool()
    async def verify_statement(self, statement: str, context: RunContext) -> str:
        """Verify a factual statement against multiple sources. Heavy background operation.

        Args:
            statement: The statement to verify.
        """

        async def _verify() -> dict:
            await asyncio.sleep(4)
            return {
                "statement": statement,
                "verdict": "partially_verified",
                "confidence": 0.78,
                "evidence": [
                    {"source": "Academic literature", "supports": True, "note": "Consistent with peer-reviewed findings"},
                    {"source": "Official statistics", "supports": True, "note": "Aligns with published data"},
                    {"source": "Expert consensus", "supports": False, "note": "Some experts express nuanced disagreement"},
                ],
                "nuance": "The core claim holds but context matters significantly.",
            }

        self._executor.submit(
            name=f"verify: {statement[:50]}",
            description=f"Fact-checking statement: {statement}",
            coro=_verify(),
            initiated_by=self.id,
            priority=TaskPriority.HIGH,
        )

        return "Verification initiated. Continue the conversation."

    @function_tool()
    async def cross_reference(self, claim: str, sources: list[str], context: RunContext) -> str:
        """Cross-reference a claim against specific sources. Heavy background operation.

        Args:
            claim: The claim to cross-reference.
            sources: List of source types to check against.
        """

        async def _cross_ref() -> dict:
            await asyncio.sleep(5)
            return {
                "claim": claim,
                "sources_checked": sources,
                "agreement_ratio": 0.85,
                "findings": [
                    {"source": src, "agrees": idx % 3 != 2, "detail": f"Source {src} {'supports' if idx % 3 != 2 else 'partially contradicts'} the claim"}
                    for idx, src in enumerate(sources)
                ],
                "overall_assessment": "Mostly corroborated with minor caveats.",
            }

        self._executor.submit(
            name=f"cross-ref: {claim[:40]}",
            description=f"Cross-referencing against {len(sources)} sources",
            coro=_cross_ref(),
            initiated_by=self.id,
            priority=TaskPriority.NORMAL,
        )

        return "Cross-reference initiated. Keep the conversation going."

    @function_tool()
    async def check_source_reliability(self, source: str, context: RunContext) -> str:
        """Check the reliability of a specific source. Light operation.

        Args:
            source: The source to evaluate.
        """
        await asyncio.sleep(0.3)
        return (
            f"Source reliability assessment for '{source}': "
            "Generally considered reliable with established track record. "
            "Peer-reviewed content available. Minor bias noted in certain areas. "
            "Overall rating: credible with standard caveats."
        )

    @function_tool()
    async def transfer_to_navigator(self, context: RunContext) -> tuple[Agent, str]:
        """Return to the main conversation flow."""
        agents: dict[str, Agent] = context.userdata.agents
        registry = self._userdata.task_registry
        completed = [t for t in registry.tasks.values() if t.initiated_by == self.id and t.status == TaskStatus.COMPLETED]

        msg = "Returning to main conversation."
        if completed:
            msg += f" {len(completed)} verification(s) completed."
        return agents["navigator"], msg

    @function_tool()
    async def transfer_to_researcher(self, context: RunContext) -> tuple[Agent, str]:
        """Hand off to the researcher for additional information gathering."""
        agents: dict[str, Agent] = context.userdata.agents
        return agents["web_searcher"], "Transitioning to research mode."
