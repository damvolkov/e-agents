# Commands Reference

## Setup

| Command | Description |
|---------|-------------|
| `make install` | Install uv, dependencies, and pre-commit hooks |
| `make sync` | Sync dependencies from lockfile |
| `make lock` | Update lockfile with current dependencies |

## Infrastructure (Docker)

| Command | Description |
|---------|-------------|
| `make infra` | Start all services (STT/TTS/LiveKit + Agent) |
| `make infra-down` | Stop all infrastructure services |
| `make logs` | Follow agent container logs |
| `make build` | Build Docker image |

## Local Development

| Command | Description |
|---------|-------------|
| `make run` | Start agent locally (dev mode + API) |
| `make console` | Start agent in console mode (local testing) |
| `make join` | Join a room as participant |
| `make token` | Generate LiveKit access token |

### Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION` | `double_loop` | Session type |
| `ROOM` | `test-room` | Room name for join/token |
| `IDENTITY` | `user` | Participant identity |
| `TTL` | `60` | Token TTL in minutes |

### Examples

```bash
make console SESSION=double_loop
make token ROOM=my-room IDENTITY=john TTL=120
make join ROOM=my-room IDENTITY=john
```

## Quality

| Command | Description |
|---------|-------------|
| `make lint` | Run ruff linter with auto-fix |
| `make format` | Format code with ruff |
| `make type` | Run type checker |
| `make test` | Run unit tests |

## Cleanup

| Command | Description |
|---------|-------------|
| `make clean` | Remove cache and build artifacts |

## API Endpoints

When the API is running (via `make run` or `make infra`):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/tokens` | POST | Generate access token |
| `/api/v1/rooms` | GET | List all rooms |
| `/api/v1/rooms` | POST | Create a room |
| `/api/v1/rooms/{name}` | DELETE | Delete a room |
| `/api/v1/rooms/{name}/participants` | GET | List participants |
| `/api/v1/dispatch` | POST | Dispatch agent to room |

API documentation: `http://localhost:8000/docs`
