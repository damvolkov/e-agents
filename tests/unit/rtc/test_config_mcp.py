"""Tests for MCP transport configuration models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from e_agents.rtc.models.config import (
    BaseTransport,
    McpConfig,
    SseTransport,
    StdioTransport,
    StreamableHttpTransport,
)

##### STDIO TRANSPORT #####


_STDIO_CASES = [
    pytest.param(
        {"command": "npx", "args": ["-y", "@upstash/context7-mcp"], "env": {"KEY": "val"}},
        id="context7-with-env",
    ),
    pytest.param(
        {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]},
        id="filesystem",
    ),
    pytest.param(
        {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-docker"]},
        id="docker",
    ),
    pytest.param(
        {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"]},
        id="memory",
    ),
    pytest.param(
        {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-postgres"],
            "env": {"PG_CONNECTION_STRING": "postgresql://u:p@localhost:5432/db"},
        },
        id="postgres-with-env",
    ),
    pytest.param(
        {"command": "uvx", "args": ["mcp-server-git", "--repository", "/tmp/repo"]},
        id="git-uvx",
    ),
    pytest.param(
        {"command": "node", "args": ["server.js"]},
        id="bare-node",
    ),
]


@pytest.mark.parametrize("data", _STDIO_CASES)
async def test_stdio_transport_validates(data: dict[str, Any]) -> None:
    transport = StdioTransport.model_validate(data)
    assert transport.transport == "stdio"
    assert transport.command == data["command"]
    assert transport.args == data.get("args", [])
    assert transport.env == data.get("env", {})


async def test_stdio_transport_defaults() -> None:
    transport = StdioTransport(command="npx")
    assert transport.args == []
    assert transport.env == {}
    assert transport.transport == "stdio"


##### SSE TRANSPORT #####


_SSE_CASES = [
    pytest.param(
        {"url": "http://localhost:5678/mcp/sse", "headers": {"Authorization": "Bearer tok"}},
        id="n8n-with-auth",
    ),
    pytest.param(
        {"url": "http://mcp.internal:3001/sse"},
        id="bare-sse",
    ),
    pytest.param(
        {"url": "https://remote.example.com/sse", "headers": {"X-Api-Key": "key123"}},
        id="remote-with-api-key",
    ),
]


@pytest.mark.parametrize("data", _SSE_CASES)
async def test_sse_transport_validates(data: dict[str, Any]) -> None:
    transport = SseTransport.model_validate(data)
    assert transport.transport == "sse"
    assert transport.url == data["url"]
    assert transport.headers == data.get("headers", {})


##### STREAMABLE HTTP TRANSPORT #####


_STREAMABLE_CASES = [
    pytest.param(
        {
            "url": "https://api.example.com/mcp",
            "headers": {"Authorization": "Bearer key", "X-Project-Id": "proj-1"},
        },
        id="cloud-with-headers",
    ),
    pytest.param(
        {"url": "http://localhost:8080/mcp/stream"},
        id="local-bare",
    ),
    pytest.param(
        {"url": "https://mcp.corp.internal/v1/stream", "headers": {"Cookie": "session=abc"}},
        id="corp-with-cookie",
    ),
]


@pytest.mark.parametrize("data", _STREAMABLE_CASES)
async def test_streamable_http_transport_validates(data: dict[str, Any]) -> None:
    transport = StreamableHttpTransport.model_validate(data)
    assert transport.transport == "streamable-http"
    assert transport.url == data["url"]
    assert transport.headers == data.get("headers", {})


##### DISCRIMINATED UNION #####


_DISCRIMINATOR_CASES = [
    pytest.param({"transport": "stdio", "command": "npx"}, StdioTransport, id="stdio"),
    pytest.param({"transport": "sse", "url": "http://x/sse"}, SseTransport, id="sse"),
    pytest.param(
        {"transport": "streamable-http", "url": "http://x/mcp"},
        StreamableHttpTransport,
        id="streamable-http",
    ),
]


@pytest.mark.parametrize(("data", "expected_type"), _DISCRIMINATOR_CASES)
async def test_mcp_config_discriminates_transport(
    data: dict[str, Any],
    expected_type: type[BaseTransport],
) -> None:
    cfg = McpConfig.model_validate({"mcpServers": {"test": data}})
    assert isinstance(cfg.mcp_servers["test"], expected_type)


##### MCP CONFIG REGISTRY #####


async def test_mcp_config_loads_mixed_registry(all_mcp_servers: dict[str, dict[str, Any]]) -> None:
    cfg = McpConfig.model_validate({"mcpServers": all_mcp_servers})
    assert len(cfg.mcp_servers) == len(all_mcp_servers)

    stdio_count = sum(1 for s in cfg.mcp_servers.values() if isinstance(s, StdioTransport))
    sse_count = sum(1 for s in cfg.mcp_servers.values() if isinstance(s, SseTransport))
    http_count = sum(1 for s in cfg.mcp_servers.values() if isinstance(s, StreamableHttpTransport))

    assert stdio_count == 7
    assert sse_count == 2
    assert http_count == 2


async def test_mcp_config_populate_by_name(all_mcp_servers: dict[str, dict[str, Any]]) -> None:
    cfg = McpConfig.model_validate({"mcp_servers": all_mcp_servers})
    assert len(cfg.mcp_servers) == len(all_mcp_servers)


##### YAML ROUNDTRIP #####


async def test_stdio_transport_roundtrip_yaml() -> None:
    raw = (
        "transport: stdio\n"
        "command: npx\n"
        "args:\n"
        "  - '-y'\n"
        "  - '@upstash/context7-mcp'\n"
        "env:\n"
        "  CONTEXT7_API_KEY: test-key\n"
    )
    transport = StdioTransport.model_validate_yaml(raw)
    assert transport.command == "npx"
    assert transport.env["CONTEXT7_API_KEY"] == "test-key"

    dumped = transport.model_dump_yaml()
    restored = StdioTransport.model_validate_yaml(dumped)
    assert restored == transport


async def test_sse_transport_roundtrip_yaml() -> None:
    raw = (
        "transport: sse\n"
        "url: http://localhost:5678/mcp/sse\n"
        "headers:\n"
        "  Authorization: 'Bearer token'\n"
    )
    transport = SseTransport.model_validate_yaml(raw)
    assert transport.url == "http://localhost:5678/mcp/sse"

    dumped = transport.model_dump_yaml()
    restored = SseTransport.model_validate_yaml(dumped)
    assert restored == transport


async def test_streamable_http_transport_roundtrip_yaml() -> None:
    raw = (
        "transport: streamable-http\n"
        "url: https://api.example.com/mcp\n"
        "headers:\n"
        "  Authorization: 'Bearer key'\n"
    )
    transport = StreamableHttpTransport.model_validate_yaml(raw)
    assert transport.url == "https://api.example.com/mcp"

    dumped = transport.model_dump_yaml()
    restored = StreamableHttpTransport.model_validate_yaml(dumped)
    assert restored == transport


async def test_mcp_config_roundtrip_yaml() -> None:
    raw = (
        "mcpServers:\n"
        "  context7:\n"
        "    transport: stdio\n"
        "    command: npx\n"
        "    args:\n"
        "      - '-y'\n"
        "      - '@upstash/context7-mcp'\n"
        "  sse-server:\n"
        "    transport: sse\n"
        "    url: http://localhost:3001/sse\n"
        "  stream-server:\n"
        "    transport: streamable-http\n"
        "    url: https://api.example.com/mcp\n"
    )
    cfg = McpConfig.model_validate_yaml(raw)
    assert len(cfg.mcp_servers) == 3
    assert isinstance(cfg.mcp_servers["context7"], StdioTransport)
    assert isinstance(cfg.mcp_servers["sse-server"], SseTransport)
    assert isinstance(cfg.mcp_servers["stream-server"], StreamableHttpTransport)


##### FROM YAML FILE #####


async def test_stdio_transport_from_yaml_file(tmp_path: Path) -> None:
    yaml_file = tmp_path / "context7.yaml"
    yaml_file.write_text(
        "transport: stdio\n"
        "command: npx\n"
        "args:\n"
        "  - '-y'\n"
        "  - '@upstash/context7-mcp'\n"
        "env:\n"
        "  CONTEXT7_API_KEY: test-key\n",
    )
    transport = StdioTransport.from_yaml(yaml_file)
    assert transport.command == "npx"
    assert len(transport.args) == 2
    assert transport.env["CONTEXT7_API_KEY"] == "test-key"


async def test_mcp_config_from_yaml_file(tmp_path: Path) -> None:
    yaml_file = tmp_path / "mcp.yaml"
    yaml_file.write_text(
        "mcpServers:\n"
        "  fs:\n"
        "    transport: stdio\n"
        "    command: npx\n"
        "    args:\n"
        "      - '-y'\n"
        "      - '@modelcontextprotocol/server-filesystem'\n"
        "  sse:\n"
        "    transport: sse\n"
        "    url: http://localhost:3001/sse\n",
    )
    cfg = McpConfig.from_yaml(yaml_file)
    assert len(cfg.mcp_servers) == 2
    assert isinstance(cfg.mcp_servers["fs"], StdioTransport)
    assert isinstance(cfg.mcp_servers["sse"], SseTransport)


##### FROZEN MODEL #####


async def test_transport_is_frozen() -> None:
    transport = StdioTransport(command="npx")
    with pytest.raises(ValidationError):
        transport.command = "node"  # type: ignore[misc]


async def test_http_transport_is_frozen() -> None:
    transport = SseTransport(url="http://localhost/sse")
    with pytest.raises(ValidationError):
        transport.url = "http://other/sse"  # type: ignore[misc]


##### EXTRA FIELDS IGNORED #####


async def test_extra_fields_ignored() -> None:
    transport = StdioTransport.model_validate({"command": "npx", "unknown_field": "value"})
    assert transport.command == "npx"
    assert not hasattr(transport, "unknown_field")


##### VALIDATION ERRORS #####


_INVALID_CASES = [
    pytest.param({"transport": "stdio"}, id="stdio-missing-command"),
    pytest.param({"transport": "sse"}, id="sse-missing-url"),
    pytest.param({"transport": "streamable-http"}, id="streamable-missing-url"),
]


@pytest.mark.parametrize("data", _INVALID_CASES)
async def test_transport_rejects_missing_required(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        McpConfig.model_validate({"mcpServers": {"bad": data}})


async def test_mcp_config_rejects_unknown_transport() -> None:
    with pytest.raises(ValidationError):
        McpConfig.model_validate({"mcpServers": {"bad": {"transport": "websocket", "url": "ws://x"}}})


async def test_mcp_config_rejects_missing_servers_key() -> None:
    with pytest.raises(ValidationError):
        McpConfig.model_validate({})
