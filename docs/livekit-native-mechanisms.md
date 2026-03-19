# LiveKit Agents — Native Mechanisms

> Runtime hooks, interruption control, and speech triggers in `livekit-agents ~= 1.4`.

---

## 1. Dynamic Instructions

LiveKit has no single `dynamic_instructions(ctx)` callback. Instead it provides four
complementary mechanisms to inject or mutate instructions at runtime.

### 1.1 — `generate_reply(instructions=...)` — Ephemeral Per-Turn

Instructions passed here are **NOT added to chat history** — they apply to a single
LLM inference call and are then discarded.

```python
async def on_enter(self) -> None:
    ud: SessionInfo = self.session.userdata
    await self.session.generate_reply(
        instructions=f"Greet {ud.user_name} by name. Their order is {ud.order_id}."
    )
```

Use case: inject userdata state, task results, or situational context into one reply.

### 1.2 — `agent.update_instructions()` — Replace Base System Prompt

Replaces the agent's base instructions **persistently** for all subsequent turns.

```python
await agent.update_instructions("New base instructions here.")
```

Use case: mode switch, language change, escalation — anything that changes the agent's
personality or scope for the rest of the session.

### 1.3 — `agent.update_chat_ctx()` — Inject into History

Adds content to the chat context. The LLM sees it in **all future turns**.

```python
ctx = self.chat_ctx.copy()
ctx.add_message(role="system", content=f"[background_data] {payload}")
await self.update_chat_ctx(ctx)
```

Use case: background task results, RAG enrichment, persistent facts the agent must
remember across turns.

### 1.4 — `on_user_turn_completed` — Hook Before Every LLM Call

Fires on every user turn, **before** the LLM generates a response. Closest equivalent
to OpenAI Agents' `dynamic_instructions`.

```python
async def on_user_turn_completed(
    self, turn_ctx: ChatContext, new_message: ChatMessage,
) -> None:
    rag = await vector_search(new_message.text_content())
    turn_ctx.add_message(role="assistant", content=f"Context: {rag}")
```

Use case: RAG injection, input guardrails, PII redaction, context enrichment.

### Summary

| Method | Persistent? | In History? | When |
|---|---|---|---|
| `generate_reply(instructions=...)` | No | No | Single LLM call |
| `update_instructions()` | Yes | No (system prompt) | All future turns |
| `update_chat_ctx()` | Yes | Yes | All future turns |
| `on_user_turn_completed` | Per-turn | Yes (via `turn_ctx`) | Before each LLM call |

---

## 2. Interruption Mechanisms

### 2.1 — Automatic (VAD-Driven)

Configured at session level. The pipeline detects user speech and interrupts the agent
automatically.

```python
session = AgentSession(
    allow_interruptions=True,            # user can cut the agent
    min_interruption_words=0,            # min transcribed words to trigger
    min_interruption_duration=0.5,       # min speech duration (seconds)
    false_interruption_timeout=2.0,      # wait before flagging false interruption
    resume_false_interruption=True,      # resume speech after false alarm
    discard_audio_if_uninterruptible=True,
)
```

Per-agent override:

```python
agent = Agent(
    instructions="...",
    allow_interruptions=False,           # override session default for this agent
)
```

### 2.2 — `session.interrupt()` — Programmatic Global

Cancels whatever the agent is doing right now (speaking, thinking, tool execution).

```python
session.interrupt()
```

### 2.3 — `handle.interrupt()` — Targeted Speech Handle

Interrupts a specific speech, not the entire session.

```python
handle = session.say("Processing your request...")
# ... later
handle.interrupt()
```

### 2.4 — `raise StopResponse()` — Abort Before Generation

Prevents the agent from responding at all. Used inside `on_user_turn_completed`.

```python
from livekit.agents import StopResponse

async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
    if is_garbage(new_message.text_content()):
        raise StopResponse()
```

### 2.5 — SpeechHandle State Inspection

After a speech completes (or is interrupted), inspect what happened.

```python
handle = session.say("Long explanation...")
await handle.wait_for_playout()

handle.interrupted   # True if cut by user or programmatically
handle.done()        # True if finished (interrupted or completed)

handle.add_done_callback(lambda _: print("speech ended"))
```

### Summary

| Mechanism | Scope | Trigger |
|---|---|---|
| VAD auto-interrupt | Session-wide | User starts speaking |
| `session.interrupt()` | Session-wide | Programmatic |
| `handle.interrupt()` | Single speech | Programmatic |
| `raise StopResponse()` | Single turn | Inside `on_user_turn_completed` |
| `allow_interruptions=False` | Per-agent or per-say | Configuration |

---

## 3. Speech Triggers

### 3.1 — `session.say()` — Predefined Text (No LLM)

TTS only. The text is known in advance.

```python
handle = session.say(
    "Hello, how can I help you?",
    allow_interruptions=False,
    add_to_chat_ctx=True,
)
await handle.wait_for_playout()
```

### 3.2 — `session.generate_reply()` — LLM-Driven

The LLM generates the response. Two input modes:

```python
# Ephemeral instructions (NOT added to history)
session.generate_reply(instructions="Greet the user warmly.")

# User input simulation (added to history)
session.generate_reply(user_input="How is the weather today?")
```

### 3.3 — Interrupt + Re-trigger Pattern

The canonical pattern for pushing new information to the agent mid-conversation:

```python
# 1. Stop current speech/generation
session.interrupt()

# 2. Optionally inject context into history
ctx = self.chat_ctx.copy()
ctx.add_message(role="system", content=f"[result] {data}")
await self.update_chat_ctx(ctx)

# 3. Re-trigger with ephemeral instruction
session.generate_reply(
    instructions="New information arrived. Share the results with the user."
)
```

### 3.4 — Pre-Synthesized Audio

Bypass TTS entirely with pre-cached audio frames:

```python
from livekit.agents.utils.audio import audio_frames_from_file

await session.say(
    "Your phrase",
    audio=audio_frames_from_file(path, sample_rate=24000, num_channels=1),
)
```

---

## 4. Lifecycle Hooks

Hooks on the `Agent` subclass that LiveKit calls automatically:

```python
class MyAgent(Agent):
    async def on_enter(self) -> None:
        """Agent becomes active (first load or handoff target)."""

    async def on_exit(self) -> None:
        """Agent is about to be replaced by another agent."""

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage,
    ) -> None:
        """User finished speaking. Fires BEFORE LLM inference."""

    async def stt_node(self, audio, model_settings):
        """Override STT processing (filter, transform transcript)."""

    async def llm_node(self, chat_ctx, tools, model_settings=None):
        """Override LLM inference (output guardrails, buffering)."""

    async def tts_node(self, text, model_settings):
        """Override TTS synthesis (text cleanup, word replacement)."""

    async def transcription_node(self, text, model_settings):
        """Override transcript sent to user (emoji removal, formatting)."""
```

---

## 5. Session Events

Events emitted by `AgentSession` for external listeners:

```python
@session.on("agent_state_changed")
def on_agent_state(ev: AgentStateChangedEvent):
    # ev.new_state: "initializing" | "idle" | "listening" | "thinking" | "speaking"
    ...

@session.on("user_state_changed")
def on_user_state(ev: UserStateChangedEvent):
    # ev.new_state: "speaking" | "listening" | "away"
    ...

@session.on("user_input_transcribed")
def on_transcript(ev):
    # ev.transcript — raw user speech text
    ...

@session.on("conversation_item_added")
def on_item(ev):
    # ev.item — new conversation item (user or agent)
    ...

@session.on("close")
def on_close(ev):
    ...
```

---

## 6. Agent Swap (Non-Tool Handoff)

```python
# Programmatic swap — no tool call needed
session.update_agent(NewAgent())

# From a tool — return the agent instance
@function_tool()
async def escalate(self, context: RunContext):
    """Escalate to manager."""
    return ManagerAgent(chat_ctx=self.chat_ctx), "Transferring to manager"
```
