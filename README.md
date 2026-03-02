<div align="center">
  <img src="main.png" alt="e-agents" width="128">
  <h1>e-agents</h1>
  <p><strong>Template for building multi-agent voice AI systems with LiveKit</strong></p>
  <p>Double-loop architecture with background tasks, agent handoffs, and real-time tracing.</p>
  <p>
    <a href="https://github.com/eagerworks/e-agents"><img src="https://img.shields.io/github/stars/eagerworks/e-agents?style=social" alt="GitHub"></a>
    <img src="https://img.shields.io/badge/python-3.12+-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  </p>
</div>

---

Built on [LiveKit Agents](https://docs.livekit.io/agents/) with self-hosted STT/TTS via Docker.

## Quick Start

1. Clone and install

```bash
git clone https://github.com/eagerworks/e-agents.git
cd e-agents
make install
```

2. Configure environment

```bash
cp env.template .env
# Edit .env with your GOOGLE_API_KEY / GEMINI_API_KEY
```

3. Start infrastructure and test

```bash
# Start LiveKit + STT + TTS services
make infra

# Run in console mode (local text-based testing)
make console
```

## Architecture

### Double Loop Pattern

```
 OUTER LOOP (user-facing)              INNER LOOP (background)
 ========================              =======================

 User <---> Navigator                  TaskExecutor
               |                         |  |  |
               |--- handoff ----------> WebSearcher
               |--- handoff ----------> Analyst
               |--- handoff ----------> FactChecker
               |                         |  |  |
               |<-- callback ---------- completed tasks
               |
               '--> natural response to user
```

**Flow:**
1. User speaks -> Navigator receives transcript
2. Navigator classifies: immediate answer OR background research needed
3. Heavy operations run as background tasks via TaskExecutor
4. Navigator keeps conversing naturally while tasks process
5. On task completion, callback triggers natural result presentation
6. Agent handoffs are transparent - all agents share the same persona

### Agents

| Agent | Loop | Role |
|-------|------|------|
| **Navigator** | Outer | Main conversational agent, routes and dispatches |
| **WebSearcher** | Inner | Web and academic search specialist |
| **Analyst** | Inner | Topic synthesis and report generation |
| **FactChecker** | Inner | Claim verification and cross-referencing |

## Commands

### Setup

| Command | Description |
|---------|-------------|
| `make install` | Install uv, dependencies, and pre-commit hooks |
| `make sync` | Sync dependencies from lockfile |
| `make lock` | Update lockfile |

### Infrastructure

| Command | Description |
|---------|-------------|
| `make infra` | Start all services (STT/TTS/LiveKit + API) |
| `make infra-down` | Stop all services |
| `make logs` | Follow API container logs |
| `make build` | Build Docker image |

### Development

| Command | Description |
|---------|-------------|
| `make run` | Start agent server (dev mode) |
| `make console` | Console mode (local text-based testing) |
| `make join` | Join a LiveKit room as participant |
| `make token` | Generate LiveKit access token |

### Quality

| Command | Description |
|---------|-------------|
| `make lint` | Ruff linter with auto-fix |
| `make format` | Ruff formatter |
| `make type` | Type checker |
| `make test` | Unit tests |

## Configuration

Environment variables in `.env`:

```env
# LiveKit
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

# STT (Whisper)
STT_BASE_URL=http://localhost:4100

# TTS (Piper)
TTS_HOST=localhost
TTS_PORT=10200

# LLM
GOOGLE_API_KEY=your-api-key
GEMINI_MODEL=gemini-2.0-flash
```

## Project Structure

```
src/e_agents/
├── agents/              # Agent definitions + config.yaml
│   ├── navigator.py     # Outer-loop dispatcher
│   ├── web_searcher.py  # Web search specialist
│   ├── analyst.py       # Analysis specialist
│   ├── fact_checker.py  # Verification specialist
│   └── config.yaml      # Agent instructions & routing
├── adapters/            # STT/TTS adapters (Whisper, Piper)
├── api/                 # FastAPI REST API
├── cli/                 # CLI commands (run, console, join, token)
├── core/                # Settings, logger
├── models/              # Pydantic models
├── operations/          # Audio processing, VAD
├── sessions/            # Double loop session orchestration
├── tasks/               # Background task executor, registry, models
└── tools/               # Shared agent tools
```

## API

Available at `http://localhost:8000` when running with `make run` or `make infra`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/tokens` | POST | Generate access token |
| `/api/v1/rooms` | GET/POST | List/create rooms |
| `/api/v1/rooms/{name}` | DELETE | Delete a room |
| `/api/v1/dispatch` | POST | Dispatch agent to room |

Docs: `http://localhost:8000/docs`

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | Double loop pattern and data flow |
| [Agents](docs/agents.md) | Agent structure, tools, and handoffs |
| [Background Tasks](docs/background-tasks.md) | Task executor, priority, and callbacks |
| [Sessions](docs/sessions.md) | Session configuration |
| [Infrastructure](docs/infrastructure.md) | Docker services |
| [Commands](docs/commands.md) | Full command reference |

## License

MIT
