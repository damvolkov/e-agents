"""Verification tool implementations."""

from __future__ import annotations

import asyncio

from livekit.agents import RunContext

from e_agents.tasks.status import TaskPriority


async def verify_claim(self, claim: str, context: RunContext) -> str:
    """Verify a factual claim. Background operation.

    Args:
        claim: The claim to verify.
    """

    async def _verify() -> dict:
        await asyncio.sleep(4)
        return {
            "claim": claim,
            "verdict": "partially_supported",
            "confidence": 0.78,
            "nuance": "Core claim holds but context matters.",
        }

    self._executor.submit(
        name=f"verify: {claim[:50]}",
        description=f"Fact-check: {claim}",
        coro=_verify(),
        initiated_by=self.id,
        priority=TaskPriority.HIGH,
    )
    return "Verification launched. Continue the conversation."


async def cross_reference(self, claim: str, sources: list[str], context: RunContext) -> str:
    """Cross-reference a claim against specific sources. Background operation.

    Args:
        claim: The claim to cross-reference.
        sources: Source types to check against.
    """

    async def _xref() -> dict:
        await asyncio.sleep(5)
        return {
            "claim": claim,
            "sources_checked": sources,
            "agreement_ratio": 0.85,
            "assessment": "Mostly corroborated with minor caveats.",
        }

    self._executor.submit(
        name=f"xref: {claim[:40]}",
        description=f"Cross-ref against {len(sources)} sources",
        coro=_xref(),
        initiated_by=self.id,
        priority=TaskPriority.NORMAL,
    )
    return "Cross-reference launched."
