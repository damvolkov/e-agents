# ReactiveSession — Design Document

> WIP. Session-level reactive state machine for real-time agent orchestration.
> Started 2026-03-19. Prototype in `scripts/reactive.py`.

---

## 1. Problem

The reactive logic (state observation, decision-making, interruption, re-triggering)
was initially placed inside the Agent (`LiveKitReactiveAgent` in `src/e_agents/arch/livekit.py`).
This is wrong because:

- **Agents are ephemeral** — they get swapped on handoffs, die on `session.update_agent()`.
  If reactive logic lives in the agent, it dies with the agent.
- **Agents shouldn't self-orchestrate** — an agent deciding when to interrupt itself
  or swap itself is circular. Orchestration belongs one level up.
- **State duplication** — N agents = N copies of reactive logic, each managing its own
  view of state instead of sharing one.

The **Session** is the persistent entity. It lives for the entire conversation.
The reactive state machine belongs at this level.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│  ReactiveSession                                        │
│  (async state machine — lives alongside AgentSession)   │
│                                                         │
│  state: ReactiveState  ←──── session.userdata           │
│  policies: tuple[Policy, ...]                           │
│                                                         │
│  Two async processes:                                   │
│  ├── Reactor (event-driven) — queue → dispatch → act    │
│  └── Ticker  (time-driven)  — interval → TICK event     │
│                                                         │
│  ACTUATORS (what it can do via SessionHandle):          │
│  ├── interrupt()                                        │
│  ├── say(text=...)                                      │
│  ├── generate_reply(instructions=...)                   │
│  ├── update_instructions(instructions=...)              │
│  └── swap_agent(agent_id=...)                           │
│                                                         │
│  OBSERVERS (where events come from):                    │
│  ├── LiveKit session events (agent_state, user_state)   │
│  ├── Agent tool completions (task results)              │
│  └── Ticker (periodic TICK)                             │
└─────────────────────────────────────────────────────────┘
         │ act on                    ▲ report to
         ▼                           │
┌─────────────────┐         ┌────────┴────────┐
│  AgentSession    │◄───────►│  Agent(s)       │
│  (LK pipeline)   │         │  (ephemeral)    │
│  VAD→STT→LLM→TTS│         │  instructions   │
│                  │         │  tools → write   │
│  session.userdata│         │  to userdata     │
└─────────────────┘         └─────────────────┘
```

### Key principle

**Agents are reporters and domain executors.** They do their job (converse, call tools),
and their tools write results to `session.userdata`. They don't know the reactive system exists.

**ReactiveSession observes and acts.** It watches state changes, evaluates policies,
and executes decisions on session/agents using framework-native mechanisms.

**The state is the contract.** Agents write to it. Policies read from it. Neither knows
about the other. `ReactiveState` in `session.userdata` is the shared boundary.

---

## 3. Taxonomy (N1)

### Entities

State, Event, Decision, Policy, Session (ReactiveSession)

### Canonical verbs

| Semantic field | Canonical | Rejected synonyms |
|---|---|---|
| start lifecycle | `run` | start, launch, begin |
| stop lifecycle | `stop` | shutdown, close, halt |
| push event | `emit` | fire, send, push, dispatch |
| evaluate rule | `evaluate` | check, match, test |
| execute action | `act` | execute, perform, do |
| apply state change | `apply` | update, mutate, set |
| format output | `format` | render, display, stringify |

### Suffixes

| Semantic field | Canonical | Rejected |
|---|---|---|
| kind enum | `Kind` | Type, Category |
| action enum | `Action` | Command, Op |
| decision result | `Decision` | Result, Outcome |
| state container | `State` | Status, Context |
| rule | `Policy` | Rule, Strategy, Guard |
| framework bridge | `Handle` | Adapter, Bridge, Proxy |

### Private prefix

`_rs_` for all private methods on `ReactiveSession`.

---

## 4. Data model

### EventKind (StrEnum)

```
USER_SPEAKING, USER_SILENT, USER_AWAY
AGENT_SPEAKING, AGENT_IDLE, AGENT_THINKING
TASK_COMPLETED, TASK_FAILED
TICK
```

### Action (StrEnum)

```
INTERRUPT, REPLY, SAY, UPDATE_INSTRUCTIONS, SWAP_AGENT
```

### Event (frozen dataclass)

```python
kind: EventKind
payload: dict[str, Any]    # event-specific data
timestamp: float           # time.monotonic
```

### Decision (frozen dataclass)

```python
action: Action
payload: dict[str, Any]    # action parameters (instructions, text, agent_id)
```

### ReactiveState (mutable dataclass)

```python
agent_state: str           # idle | listening | thinking | speaking
user_state: str            # speaking | listening | away
turn_count: int            # incremented on USER_SILENT after USER_SPEAKING
last_user_activity: float  # monotonic timestamp
data: dict[str, Any]       # arbitrary shared data (task results, flags)
```

---

## 5. Protocols

### SessionHandle

Framework-agnostic interface. Each agent framework provides one implementation.

```python
@runtime_checkable
class SessionHandle(Protocol):
    async def interrupt(self) -> None: ...
    async def say(self, *, text: str) -> None: ...
    async def generate_reply(self, *, instructions: str) -> None: ...
    async def update_instructions(self, *, instructions: str) -> None: ...
    async def swap_agent(self, *, agent_id: str) -> None: ...
```

Implementations:
- `ConsoleSession` — prints actions (testing)
- `LiveKitSession` (TODO) — wraps `AgentSession` + active `Agent`

### Policy

```python
class Policy(Protocol):
    def evaluate(self, state: ReactiveState, event: Event) -> tuple[Decision, ...]: ...
```

Policies are **sync** (fast evaluation, no I/O). They return zero or more Decisions.
Policies may have private state (e.g., `_notified` flag in `AwayPolicy`).
Policies are evaluated in order; all matching policies execute (no short-circuit).

---

## 6. ReactiveSession — processing flow

```
emit(event) ──→ queue ──→ reactor loop picks up
                              │
                              ▼
                         _rs_apply(event)
                         update ReactiveState from event
                              │
                              ▼
                         for policy in policies:
                             decisions = policy.evaluate(state, event)
                             for decision in decisions:
                                 _rs_act(decision)
                                     │
                                     ▼
                                 session_handle.interrupt() / .say() / .generate_reply() / ...
```

Ticker loop runs independently:

```
sleep(tick_interval) ──→ emit(Event(kind=TICK)) ──→ same pipeline
```

### State auto-update rules (_rs_apply)

| Event | State mutation |
|---|---|
| USER_SPEAKING | user_state="speaking", last_user_activity=now |
| USER_SILENT | user_state="listening", turn_count++ (if was speaking), last_user_activity=now |
| USER_AWAY | user_state="away" |
| AGENT_SPEAKING | agent_state="speaking" |
| AGENT_IDLE | agent_state="idle" |
| AGENT_THINKING | agent_state="thinking" |
| TASK_COMPLETED/FAILED | data.update(payload) |
| TICK | (no state change — policies evaluate time-based conditions) |

---

## 7. LiveKit native mechanisms used

These are the LiveKit APIs that `SessionHandle` maps to. Documented in
`docs/livekit-native-mechanisms.md`.

### Dynamic instructions (4 mechanisms)

| Method | Persistent? | In history? | When |
|---|---|---|---|
| `generate_reply(instructions=...)` | No | No | Single LLM call |
| `update_instructions()` | Yes | No (system prompt) | All future turns |
| `update_chat_ctx()` | Yes | Yes | All future turns |
| `on_user_turn_completed` hook | Per-turn | Yes (via turn_ctx) | Before each LLM call |

### Interruption

| Mechanism | Scope |
|---|---|
| VAD auto-interrupt | Session (config) |
| `session.interrupt()` | Session-wide programmatic |
| `handle.interrupt()` | Single speech |
| `raise StopResponse()` | Single turn (inside hook) |

### Speech triggers

| Method | Source | In history? |
|---|---|---|
| `session.say(text)` | Predefined text, TTS only | Optional (add_to_chat_ctx) |
| `session.generate_reply(instructions=...)` | LLM-generated | instructions: No, user_input: Yes |

### Agent swap

| Method | Mechanism |
|---|---|
| `session.update_agent(NewAgent())` | Programmatic, no tool needed |
| Tool returns `(NewAgent(), "message")` | Tool-driven handoff |

---

## 8. Example policies (in prototype)

### AwayPolicy

On TICK, if `now - last_user_activity > timeout` and not already notified:
→ `SAY("Are you still there?")`

Resets when user speaks again.

### TaskCompletedPolicy

On TASK_COMPLETED: → `INTERRUPT` + `REPLY(instructions="Share this result: {msg}")`
On TASK_FAILED: → `REPLY(instructions="A background task failed: {error}")`

### TurnEscalationPolicy

On USER_SILENT, if `turn_count >= threshold` and not already escalated:
→ `UPDATE_INSTRUCTIONS("Conversation taking too long...")` + `SWAP_AGENT(agent_id="escalation")`

---

## 9. Agent interaction model

Agents don't know about ReactiveSession. They interact via:

1. **Tools write to state**: Agent tools call `context.userdata.data["key"] = value`.
   This mutates the shared ReactiveState. The reactive system picks up changes via events.

2. **Instructions are externally controlled**: ReactiveSession can call
   `update_instructions()` on the active agent at any time based on state.

3. **`on_user_turn_completed` reads state**: The agent's hook reads from
   `session.userdata` to inject context before each LLM call. This is the natural
   place for state-driven instruction injection without coupling to the reactive system.

```python
# Agent hook — reads shared state, no knowledge of ReactiveSession
async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
    state: ReactiveState = self.session.userdata
    if state.data.get("pending_results"):
        turn_ctx.add_message(role="system", content=format_results(state.data))
```

---

## 10. Framework portability

The architecture separates framework-agnostic from framework-specific:

### Framework-agnostic (portable to any agent framework)

- `ReactiveState` — dataclass
- `Event`, `Decision` — data
- `EventKind`, `Action` — enums
- `Policy` — protocol
- `ReactiveSession` — core logic (reactor + ticker + dispatch)

### Framework-specific (one implementation per framework)

- `SessionHandle` implementation (bridges native session/agent APIs)
- `EventKind` values (may need framework-specific events)
- `_rs_apply()` rules (maps framework events to state mutations)
- Event source wiring (subscribe to framework events, emit into reactor)

### To port to another framework

1. Implement `SessionHandle` wrapping the framework's session/agent APIs
2. Wire framework events → `reactive.emit(Event(...))`
3. Adjust `_rs_apply()` if the framework has different state transitions
4. Policies remain unchanged — they only see `ReactiveState` + `Event`

---

## 11. Prototype

Working console prototype: `scripts/reactive.py` (~310 lines).

Run interactively:

```bash
uv run python scripts/reactive.py
```

Commands:

```
speak            User starts speaking
silent           User stops speaking (increments turn)
away             User goes away
done <msg>       Background task completed
fail <msg>       Background task failed
set <k> <v>      Set state.data[key] = value
state            Print current state
help             Show commands
quit             Exit
```

Example session:

```
> speak
  [EVENT   ] user_speaking
  [STATE   ] user=speaking agent=idle turns=0
> silent
  [EVENT   ] user_silent
  [STATE   ] user=listening agent=idle turns=1
> done weather is sunny 22C
  [EVENT   ] task_completed {'message': 'weather is sunny 22C'}
  [STATE   ] user=listening agent=idle turns=1 data={'message': 'weather is sunny 22C'}
  [POLICY  ] TaskCompletedPolicy -> 2 decision(s)
  [ACTION ] interrupt()
  [ACTION ] generate_reply(instructions='Share this result with the user: weather is sunny 22C')
```

---

## 12. Next steps

- [ ] `LiveKitSession` — `SessionHandle` wrapping real `AgentSession` + active `Agent`
- [ ] Event source wiring — subscribe to LiveKit session events, emit into reactor
- [ ] Integrate with existing `src/e_agents/arch/` (replace `ReactiveOps` on agent)
- [ ] Policy library — more policies for common patterns (silence detection, context
      injection, multi-agent coordination)
- [ ] State persistence — optionally persist `ReactiveState` to Redis for recovery
- [ ] `on_user_turn_completed` integration — agent hook reads from shared state
      for per-turn instruction injection (state-driven, no coupling)
- [ ] Evaluate whether `_rs_apply()` should be configurable (state transition table)
      or if subclassing `ReactiveSession` per framework is cleaner
- [ ] Consider `UPDATE_CHAT_CTX` and `UPDATE_TOOLS` as additional Actions

---

## 13. Files

| File | Purpose |
|---|---|
| `scripts/reactive.py` | Console prototype (all-in-one) |
| `docs/livekit-native-mechanisms.md` | LiveKit native APIs reference |
| `docs/livekit-howto-build.md` | LiveKit SDK build guide (~1.4) |
| `src/e_agents/arch/livekit.py` | Current agent-level reactive impl (to be replaced) |
| `src/e_agents/arch/models.py` | Current reactive models (Event, TaskStatus, etc.) |
