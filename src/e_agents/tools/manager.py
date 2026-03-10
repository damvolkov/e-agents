"""Tool registry: maps YAML tool names to Python function implementations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from e_agents.tools import analysis, research, scraper, system, verification

type ToolFn = Callable[..., Any]

_TOOL_REGISTRY: dict[str, ToolFn] = {
    "research_topic": research.research_topic,
    "quick_lookup": research.quick_lookup,
    "search_web": research.search_web,
    "search_academic": research.search_academic,
    "compare_topics": analysis.compare_topics,
    "generate_report": analysis.generate_report,
    "verify_claim": verification.verify_claim,
    "cross_reference": verification.cross_reference,
    "check_background_tasks": system.check_background_tasks,
    "scrape_url": scraper.scrape_url,
    "scrape_search": scraper.scrape_search,
    "extract_links": scraper.extract_links,
}


def get_tool(name: str) -> ToolFn:
    """Resolve a tool function by its YAML name."""
    fn = _TOOL_REGISTRY.get(name)
    if fn is None:
        available = sorted(_TOOL_REGISTRY)
        raise KeyError(f"Unknown tool '{name}'. Available: {available}")
    return fn


def register_tool(name: str, fn: ToolFn) -> None:
    """Register a custom tool at runtime."""
    _TOOL_REGISTRY[name] = fn


def all_tool_names() -> list[str]:
    """All registered tool names."""
    return sorted(_TOOL_REGISTRY)
