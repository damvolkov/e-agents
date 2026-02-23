# Architecture

## Double Loop Pattern

The **Double Loop** architecture separates user-facing conversation (outer loop) from background research and processing (inner loop). The user always talks to a single coherent persona while specialist agents work behind the scenes.

```
 OUTER LOOP                              INNER LOOP
 ==========                              ==========

 ┌──────────┐    handoff    ┌─────────────┐    handoff    ┌──────────┐
 │Navigator │◄─────────────►│ WebSearcher │◄─────────────►│ Analyst  │
 │ (Front)  │               │  (Search)   │               │(Synth.)  │
 └────┬─────┘               └──────┬──────┘               └────┬─────┘
      │                            │                            │
      │    handoff    ┌────────────┘                            │
      │◄─────────────►│ FactChecker │◄──────────────────────────┘
      │               │  (Verify)   │
      │               └──────┬──────┘
      │                      │
      ▼                      ▼
 ┌──────────────────────────────────────────────────────┐
 │                  TASK EXECUTOR                       │
 │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐    │
 │  │Task[H] │  │Task[N] │  │Task[H] │  │Task[L] │    │
 │  │Running │  │Pending │  │Complete│  │Running │    │
 │  └───┬────┘  └────────┘  └───┬────┘  └────────┘    │
 │      └────────────────────────┘                      │
 │                    │                                 │
 │                    ▼                                 │
 │        ┌─────────────────────┐                      │
 │        │  ON_TASK_COMPLETED  │                      │
 │        │   generate_reply()  │                      │
 │        └─────────────────────┘                      │
 └──────────────────────────────────────────────────────┘
```

## Key Design Principles

1. **Unified persona**: All agents share the same user-facing identity. The user never knows they are talking to different agents.
2. **Natural language**: Task completion is presented through `generate_reply()` with instructions, never hardcoded strings. The LLM formulates natural responses.
3. **Priority queue**: Tasks carry `HIGH`, `NORMAL`, or `LOW` priority. High-priority notifications are delivered first.
4. **Transparent handoffs**: Agent transfers happen seamlessly without the user being informed of the switch.

## Components

### Agent Types

| Agent | Loop | Description |
|-------|------|-------------|
| **Navigator** | Outer | Main dispatcher, classifies requests, manages conversation flow |
| **WebSearcher** | Inner | Web and academic search capabilities |
| **Analyst** | Inner | Topic synthesis, comparison, report generation |
| **FactChecker** | Inner | Claim verification, source evaluation |

### Core Modules

```
src/e_template_agents/
├── adapters/          # STT/TTS adapters (Whisper, Piper)
├── agents/            # Agent definitions with tools
├── core/
│   ├── logger.py      # LiveKit-native logging with icons
│   └── settings.py    # Pydantic settings from .env
├── tasks/
│   ├── executor.py    # Background task executor
│   ├── models.py      # Task data models with priority
│   ├── registry.py    # Task registry with priority ordering
│   └── status.py      # TaskStatus + TaskPriority enums
├── sessions/
│   └── double_loop.py # Session with event handlers
└── __main__.py        # Entry point
```

## Data Flow

1. **User speaks** -> STT -> transcript
2. **Transcript** -> LLM (with agent instructions + tools)
3. **LLM decides** -> call tool OR respond directly
4. **Tool execution** -> may trigger background task or agent handoff
5. **Background task** -> runs async, calls callback on completion
6. **Callback** -> `generate_reply()` with findings as instructions
7. **LLM formulates** -> natural response presenting results as its own
