# Sessions

Sessions define the entry point and configuration for voice agent interactions.

## Available Sessions

### Double Loop (`double_loop`)

The primary session implementing the double loop architecture with background tasks and agent handoffs.

```bash
make run SESSION=double_loop
make console SESSION=double_loop
```

**Features:**
- Navigator agent as outer-loop dispatcher
- WebSearcher, Analyst, and FactChecker as inner-loop specialists
- Background task execution with priority and callbacks
- Native LiveKit event tracing
- Transparent agent handoffs with unified persona

## Session Configuration

Sessions are selected via the `SESSION` variable:

```bash
make console                       # default: double_loop
make console SESSION=double_loop   # explicit
```

## Creating a New Session

1. Create session file in `sessions/`:

```python
from dataclasses import dataclass, field
from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions

@dataclass
class MyUserData:
    agents: dict[str, Agent] = field(default_factory=dict)

class MySession:
    def __init__(self) -> None:
        self._session: AgentSession[MyUserData] | None = None

    async def entrypoint(self, ctx: agents.JobContext) -> None:
        await ctx.connect()
        # setup agents, session, event handlers
```

2. Register in `cli/sessions.py`:

```python
SESSIONS = {
    "double_loop": DoubleLoopSession,
    "my_session": MySession,
}
```
