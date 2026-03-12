"""Tests for Builder — agent assembly, handoffs, background tools, session state."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from livekit.agents import NOT_GIVEN as _NG
from livekit.agents import Agent, function_tool
from livekit.agents.llm import FunctionTool

from e_agents.rtc.core.exceptions import SessionBuildError
from e_agents.rtc.models.config import (
    AgentConfig,
    ExecutionConfig,
    HandoffConfig,
    SessionConfig,
    ToolRef,
)
from e_agents.rtc.models.state import SessionState
from e_agents.rtc.operations.build import Builder
from e_agents.rtc.operations.load import Config
from e_agents.rtc.operations.queue import TaskQueue
from e_agents.shared.models import LLMConfig
from e_agents.shared.state import State

##### FIXTURES #####


@pytest.fixture
def shared_state() -> State:
    """Process-level shared state with a mock adapter."""
    state = State()
    adapter = MagicMock()
    adapter.name = "searxng"
    adapter.tools = []
    adapter.mcp_servers = []
    state.register_adapter(adapter)
    return state


@pytest.fixture
def mock_web_search() -> FunctionTool:
    """Real FunctionTool for testing tool wiring."""

    @function_tool(name="web_search")
    async def _search(context: Any) -> str:
        """Search the web."""
        return "mock result"

    return _search


@pytest.fixture
def agent_cfgs() -> dict[str, AgentConfig]:
    """Three-agent handoff chain: assistant -> scraper / researcher -> assistant."""
    return {
        "assistant": AgentConfig.model_validate({
            "name": "assistant",
            "instructions": "Helpful assistant.",
            "greeting": "Hello! How can I help?",
            "tools": ["web_search"],
            "handoffs": ["scraper", "researcher"],
        }),
        "scraper": AgentConfig.model_validate({
            "name": "scraper",
            "instructions": "Search specialist.",
            "tools": ["web_search"],
            "handoffs": ["assistant"],
        }),
        "researcher": AgentConfig.model_validate({
            "name": "researcher",
            "instructions": "Deep research analyst.",
            "tools": ["web_search"],
            "handoffs": ["assistant"],
        }),
    }


@pytest.fixture
def session_cfg() -> SessionConfig:
    return SessionConfig.model_validate({
        "name": "test",
        "stt": "whisperlive",
        "tts": "kokoro",
        "vad": "silero",
        "llm": {"provider": "google", "model": "gemini-2.0-flash"},
        "dispatcher": "assistant",
        "agents": ["assistant", "scraper", "researcher"],
        "state": ["user_name", "topic"],
    })


@pytest.fixture
def session_cfg_with_queue() -> SessionConfig:
    return SessionConfig.model_validate({
        "name": "queued",
        "stt": "whisperlive",
        "tts": "kokoro",
        "vad": "silero",
        "llm": {"provider": "google", "model": "gemini-2.0-flash"},
        "dispatcher": "assistant",
        "agents": ["assistant", "scraper"],
        "task_queue": {"enabled": True, "max_concurrent": 2},
    })


@pytest.fixture
def mock_registry(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace ProviderRegistry in builder module with a full mock."""
    registry = MagicMock()
    registry.create_stt.return_value = MagicMock()
    registry.create_tts.return_value = MagicMock()
    registry.create_vad.return_value = MagicMock()
    monkeypatch.setattr("e_agents.rtc.operations.build.ProviderRegistry", registry)
    return registry


@pytest.fixture
def builder(
    agent_cfgs: dict[str, AgentConfig],
    session_cfg: SessionConfig,
    mock_web_search: FunctionTool,
    mock_registry: MagicMock,
) -> Builder:
    """Builder with pre-loaded config and mocked providers."""
    b = Builder()
    b.config = Config(agents=agent_cfgs, sessions={"test": session_cfg}, mcps={})
    b.tools = {"web_search": mock_web_search}
    return b


@pytest.fixture
def builder_with_queue(
    agent_cfgs: dict[str, AgentConfig],
    session_cfg_with_queue: SessionConfig,
    mock_web_search: FunctionTool,
    mock_registry: MagicMock,
) -> Builder:
    """Builder with task queue enabled."""
    bg_assistant = AgentConfig.model_validate({
        "name": "assistant",
        "instructions": "Helpful assistant.",
        "greeting": "Hello!",
        "tools": [
            {"name": "web_search", "execution": {"mode": "background", "pre_response": {"enabled": True, "message": "Searching..."}}, "priority": 2},
        ],
        "handoffs": ["scraper"],
        "execution": {
            "mode": "background",
            "cancellation": {"enabled": True},
        },
    })
    scraper = AgentConfig.model_validate({
        "name": "scraper",
        "instructions": "Search specialist.",
        "tools": ["web_search"],
        "handoffs": ["assistant"],
    })
    cfgs = {"assistant": bg_assistant, "scraper": scraper}
    b = Builder()
    b.config = Config(agents=cfgs, sessions={"queued": session_cfg_with_queue}, mcps={})
    b.tools = {"web_search": mock_web_search}
    return b


##### SESSION STATE #####


async def test_session_state_delegates_get_adapter(shared_state: State) -> None:
    ss = SessionState(shared=shared_state)
    adapter = ss.get_adapter("searxng")
    assert adapter.name == "searxng"


async def test_session_state_data_empty_by_default() -> None:
    ss = SessionState(shared=State())
    assert ss.data == {}


async def test_session_state_data_from_config(shared_state: State) -> None:
    ss = SessionState(shared=shared_state, data={"user_name": None, "topic": None})
    assert "user_name" in ss.data
    assert "topic" in ss.data
    ss.data["user_name"] = "Alice"
    assert ss.data["user_name"] == "Alice"


async def test_session_state_adapters_delegation(shared_state: State) -> None:
    ss = SessionState(shared=shared_state)
    assert len(ss.adapters) == 1
    assert ss.adapters[0].name == "searxng"


async def test_session_state_task_queue_default() -> None:
    ss = SessionState(shared=State())
    assert ss.task_queue is None


async def test_session_state_task_queue_injected() -> None:
    queue = TaskQueue(max_concurrent=2)
    ss = SessionState(shared=State(), task_queue=queue)
    assert ss.task_queue is queue


##### AGENT BUILDING #####


async def test_builder_build_agent_creates_agent(builder: Builder) -> None:
    session_cfg = builder.config.sessions["test"]
    agent = builder._bd_build_agent("scraper", session_cfg)
    assert isinstance(agent, Agent)
    assert agent.instructions == "Search specialist."


async def test_builder_build_agent_with_greeting_creates_subclass(builder: Builder) -> None:
    session_cfg = builder.config.sessions["test"]
    agent = builder._bd_build_agent("assistant", session_cfg)
    assert isinstance(agent, Agent)
    assert type(agent).__name__ == "Agent_assistant"
    assert hasattr(agent, "on_enter")


async def test_builder_build_agent_without_greeting_is_plain(builder: Builder) -> None:
    session_cfg = builder.config.sessions["test"]
    agent = builder._bd_build_agent("scraper", session_cfg)
    assert type(agent) is Agent


async def test_builder_build_agent_includes_tools(builder: Builder) -> None:
    session_cfg = builder.config.sessions["test"]
    agent = builder._bd_build_agent("scraper", session_cfg)
    tool_names = {t.info.name for t in agent.tools if hasattr(t, "info")}
    assert "web_search" in tool_names


async def test_builder_build_agent_includes_handoff_tools(builder: Builder) -> None:
    session_cfg = builder.config.sessions["test"]
    agent = builder._bd_build_agent("assistant", session_cfg)
    tool_names = {t.info.name for t in agent.tools if hasattr(t, "info")}
    assert "transfer_to_scraper" in tool_names
    assert "transfer_to_researcher" in tool_names


async def test_builder_build_agent_raises_for_unknown(builder: Builder) -> None:
    session_cfg = builder.config.sessions["test"]
    with pytest.raises(SessionBuildError, match="not found"):
        builder._bd_build_agent("nonexistent", session_cfg)


##### DYNAMIC AGENT CLASS #####


async def test_builder_agent_class_plain_when_no_hooks() -> None:
    cfg = AgentConfig.model_validate({"name": "plain", "instructions": "No greeting."})
    cls = Builder._bd_agent_class("plain", cfg, has_queue=False)
    assert cls is Agent


async def test_builder_agent_class_subclass_with_greeting() -> None:
    cfg = AgentConfig.model_validate({"name": "greeter", "greeting": "Hi!"})
    cls = Builder._bd_agent_class("greeter", cfg, has_queue=False)
    assert cls is not Agent
    assert issubclass(cls, Agent)
    assert cls.__name__ == "Agent_greeter"


async def test_builder_agent_class_subclass_with_queue() -> None:
    cfg = AgentConfig.model_validate({"name": "worker", "instructions": "Work."})
    cls = Builder._bd_agent_class("worker", cfg, has_queue=True)
    assert cls is not Agent
    assert issubclass(cls, Agent)
    assert hasattr(cls, "on_user_turn_completed")


##### HANDOFF #####


async def test_builder_handoff_creates_function_tool(builder: Builder) -> None:
    session_cfg = builder.config.sessions["test"]
    handoff = HandoffConfig(target="scraper")
    tool = builder._bd_build_handoff(handoff, session_cfg)
    assert isinstance(tool, FunctionTool)
    assert tool.info.name == "transfer_to_scraper"


async def test_builder_handoff_tool_returns_agent(builder: Builder) -> None:
    session_cfg = builder.config.sessions["test"]
    handoff = HandoffConfig(target="scraper")
    tool = builder._bd_build_handoff(handoff, session_cfg)

    mock_ctx = MagicMock()
    mock_ctx.session.current_agent.chat_ctx = MagicMock()
    result = await tool(mock_ctx)
    assert isinstance(result, Agent)
    assert result.instructions == "Search specialist."


async def test_builder_handoff_fresh_context(builder: Builder) -> None:
    session_cfg = builder.config.sessions["test"]
    handoff = HandoffConfig(target="scraper", context="fresh")
    tool = builder._bd_build_handoff(handoff, session_cfg)

    mock_ctx = MagicMock()
    mock_ctx.session.current_agent.chat_ctx = MagicMock()
    result = await tool(mock_ctx)
    assert isinstance(result, Agent)


async def test_builder_handoff_custom_description(builder: Builder) -> None:
    session_cfg = builder.config.sessions["test"]
    handoff = HandoffConfig(target="scraper", description="Custom transfer.")
    tool = builder._bd_build_handoff(handoff, session_cfg)
    assert "Custom transfer" in tool.info.description


async def test_builder_handoff_chain_circular(builder: Builder) -> None:
    """Verify assistant -> scraper -> assistant chain doesn't loop at build time."""
    session_cfg = builder.config.sessions["test"]
    assistant = builder._bd_build_agent("assistant", session_cfg)

    handoff_names = {t.info.name for t in assistant.tools if hasattr(t, "info")}
    assert "transfer_to_scraper" in handoff_names

    ws_handoff = next(
        t for t in assistant.tools if hasattr(t, "info") and t.info.name == "transfer_to_scraper"
    )
    mock_ctx = MagicMock()
    mock_ctx.session.current_agent.chat_ctx = MagicMock()
    scraper = await ws_handoff(mock_ctx)

    ws_tool_names = {t.info.name for t in scraper.tools if hasattr(t, "info")}
    assert "transfer_to_assistant" in ws_tool_names


##### BACKGROUND TOOLS #####


async def test_builder_wraps_background_tool(builder_with_queue: Builder) -> None:
    session_cfg = builder_with_queue.config.sessions["queued"]
    agent = builder_with_queue._bd_build_agent("assistant", session_cfg)
    tool_names = {t.info.name for t in agent.tools if hasattr(t, "info")}
    assert "web_search" in tool_names


async def test_builder_background_tool_returns_pre_response(builder_with_queue: Builder) -> None:
    session_cfg = builder_with_queue.config.sessions["queued"]
    agent = builder_with_queue._bd_build_agent("assistant", session_cfg)

    bg_tool = next(t for t in agent.tools if hasattr(t, "info") and t.info.name == "web_search")
    mock_ctx = MagicMock()
    mock_ctx.userdata.task_queue = TaskQueue(max_concurrent=2)

    result = await bg_tool(mock_ctx)
    assert result == "Searching..."


async def test_builder_background_tool_submits_to_queue(builder_with_queue: Builder) -> None:
    session_cfg = builder_with_queue.config.sessions["queued"]
    agent = builder_with_queue._bd_build_agent("assistant", session_cfg)

    bg_tool = next(t for t in agent.tools if hasattr(t, "info") and t.info.name == "web_search")
    queue = TaskQueue(max_concurrent=2)
    mock_ctx = MagicMock()
    mock_ctx.userdata.task_queue = queue

    await bg_tool(mock_ctx)
    assert not queue.is_empty or len(queue._completed) > 0 or len(queue._running) > 0


##### CANCEL TOOLS #####


async def test_builder_cancel_tools_injected(builder_with_queue: Builder) -> None:
    session_cfg = builder_with_queue.config.sessions["queued"]
    agent = builder_with_queue._bd_build_agent("assistant", session_cfg)
    tool_names = {t.info.name for t in agent.tools if hasattr(t, "info")}
    assert "cancel_task" in tool_names
    assert "cancel_all_tasks" in tool_names
    assert "list_tasks" in tool_names


async def test_builder_cancel_tool_no_queue() -> None:
    tools = Builder._bd_build_cancel_tools()
    cancel_tool = next(t for t in tools if t.info.name == "cancel_task")
    mock_ctx = MagicMock()
    mock_ctx.userdata.task_queue = None
    result = await cancel_tool(mock_ctx, task_name="test")
    assert "No task queue" in result


async def test_builder_list_tasks_empty() -> None:
    tools = Builder._bd_build_cancel_tools()
    list_tool = next(t for t in tools if t.info.name == "list_tasks")
    mock_ctx = MagicMock()
    mock_ctx.userdata.task_queue = TaskQueue(max_concurrent=2)
    result = await list_tool(mock_ctx)
    assert "No tasks" in result


##### SESSION BUILDING #####


async def test_builder_build_creates_session_and_dispatcher(
    builder: Builder, shared_state: State,
) -> None:
    agent_session, dispatcher = builder.build("test", shared_state)
    assert isinstance(dispatcher, Agent)
    assert dispatcher.instructions == "Helpful assistant."
    assert agent_session.userdata.data == {"user_name": None, "topic": None}


async def test_builder_build_session_state_has_shared_adapters(
    builder: Builder, shared_state: State,
) -> None:
    agent_session, _ = builder.build("test", shared_state)
    ss: SessionState = agent_session.userdata
    assert ss.get_adapter("searxng").name == "searxng"


async def test_builder_build_session_with_queue(
    builder_with_queue: Builder, shared_state: State, mock_registry: MagicMock,
) -> None:
    agent_session, _ = builder_with_queue.build("queued", shared_state)
    ss: SessionState = agent_session.userdata
    assert ss.task_queue is not None
    assert isinstance(ss.task_queue, TaskQueue)


async def test_builder_build_session_without_queue(
    builder: Builder, shared_state: State,
) -> None:
    agent_session, _ = builder.build("test", shared_state)
    ss: SessionState = agent_session.userdata
    assert ss.task_queue is None


async def test_builder_build_dispatcher_is_first_agent_when_no_dispatcher(
    builder: Builder, shared_state: State,
) -> None:
    cfg = builder.config.sessions["test"]
    builder.config.sessions["test"] = SessionConfig.model_validate({
        **cfg.model_dump(), "dispatcher": "",
    })
    _, dispatcher = builder.build("test", shared_state)
    assert dispatcher.instructions == "Helpful assistant."


async def test_builder_build_raises_for_unknown_session(
    builder: Builder, shared_state: State,
) -> None:
    with pytest.raises(SessionBuildError, match="not found"):
        builder.build("nonexistent", shared_state)


##### LLM RESOLVER #####


_LLM_CASES = [
    pytest.param(None, True, id="none-returns-not-given"),
    pytest.param("gpt-4o", False, id="string-passthrough"),
    pytest.param({"provider": "google", "model": "gemini-2.0-flash"}, False, id="config-formats"),
]


@pytest.mark.parametrize(("llm_input", "expect_not_given"), _LLM_CASES)
async def test_builder_resolve_llm(
    builder: Builder, llm_input: Any, expect_not_given: bool,
) -> None:
    cfg = LLMConfig.model_validate(llm_input) if isinstance(llm_input, dict) else llm_input
    result = Builder._bd_resolve_llm(cfg)

    if expect_not_given:
        assert result is _NG
    elif isinstance(llm_input, str):
        assert result == llm_input
    else:
        assert hasattr(result, "chat"), "LLMConfig should return an LLM plugin instance"
