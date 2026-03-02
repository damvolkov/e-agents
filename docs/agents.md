# Agents

Agents are the core building blocks of the voice AI system. Each agent has specific instructions, tools, and routing capabilities.

## Agent Structure

All agents inherit from `livekit.agents.Agent` and accept an `AgentConfig` for their system prompt:

```python
from livekit.agents import Agent, RunContext, function_tool
from e_agents.models.agent import AgentConfig

class MyAgent(Agent):
    def __init__(self, config: AgentConfig) -> None:
        super().__init__(instructions=config.instructions)
        self._config = config

    @function_tool()
    async def my_tool(self, query: str, context: RunContext) -> str:
        """Tool description for the LLM."""
        return "Result"
```

## Available Agents

### Navigator (Outer Loop)

Main conversational agent. Routes requests and manages conversation flow.

**Tools:**
- `research_topic(topic)` - Deep background research (heavy)
- `quick_lookup(query)` - Fast factual lookup (light)
- `deep_analysis(topic)` - Multi-dimensional analysis (heavy)
- `verify_claim(claim)` - Fact verification (heavy)
- `transfer_to_researcher` - Handoff to web searcher
- `transfer_to_analyst` - Handoff to analyst
- `transfer_to_fact_checker` - Handoff to fact checker
- `check_background_tasks` - Internal task status

### WebSearcher (Inner Loop)

Specialist for web-based information retrieval.

**Tools:**
- `search_web(query)` - Web search (heavy)
- `search_academic(query)` - Scholarly search (heavy)
- `get_page_summary(url)` - Page summary (light)
- `transfer_to_navigator` - Return to main flow
- `transfer_to_analyst` - Handoff to analyst

### Analyst (Inner Loop)

Specialist for information synthesis and analysis.

**Tools:**
- `compare_sources(topics)` - Compare viewpoints (heavy)
- `summarize_topic(content)` - Quick summary (light)
- `generate_report(topic)` - Full analytical report (heavy)
- `transfer_to_navigator` - Return to main flow
- `transfer_to_researcher` - Handoff to researcher
- `transfer_to_fact_checker` - Handoff to fact checker

### FactChecker (Inner Loop)

Specialist for claim verification and source evaluation.

**Tools:**
- `verify_statement(statement)` - Verify a claim (heavy)
- `cross_reference(claim, sources)` - Cross-reference (heavy)
- `check_source_reliability(source)` - Source eval (light)
- `transfer_to_navigator` - Return to main flow
- `transfer_to_researcher` - Handoff to researcher

## Agent Handoffs

When a tool returns a `(Agent, str)` tuple, LiveKit performs an automatic handoff:

```python
@function_tool()
async def transfer_to_analyst(self, context: RunContext) -> tuple[Agent, str]:
    agents: dict[str, Agent] = context.userdata.agents
    return agents["analyst"], "Transitioning to analysis mode."
```

All agents share the same persona. The user experiences seamless transitions.

## Background Tasks

Heavy tools submit work to the `TaskExecutor` and return immediately:

```python
@function_tool()
async def research_topic(self, topic: str, context: RunContext) -> str:
    async def _deep_research() -> dict:
        await asyncio.sleep(5)
        return {"findings": "..."}

    self._executor.submit(
        name=topic,
        description=f"Deep research on: {topic}",
        coro=_deep_research(),
        initiated_by=self.id,
        priority=TaskPriority.HIGH,
    )
    return "Research initiated. Engage the user naturally while processing completes."
```

The tool return string is an **instruction for the LLM**, not user-facing text. The LLM then generates a natural conversational response.

## Configuration

Agent instructions and routing are defined in `agents/config.yaml`. See the config file for the full system prompts.
