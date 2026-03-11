# LiveKit Agent Actions — Complete Reference

> Exhaustive enumeration of every agent capability in `livekit-agents ~= 1.4`.
> Ordered from simplest to most complex. Each section is a discrete manipulation
> that can be composed dynamically at runtime.

---

## Table of Contents

1. [Agent Greeting & Initial Speech](#1-agent-greeting--initial-speech)
2. [Agent Lifecycle Hooks](#2-agent-lifecycle-hooks)
3. [Speech & Audio Control](#3-speech--audio-control)
4. [Instructions & Persona](#4-instructions--persona)
5. [Tools — Function Tools](#5-tools--function-tools)
6. [Tool Interruption & Speech Control](#6-tool-interruption--speech-control)
7. [Dynamic Tool Management](#7-dynamic-tool-management)
8. [State Management — Userdata](#8-state-management--userdata)
9. [Handoffs — Multi-Agent Routing](#9-handoffs--multi-agent-routing)
10. [Context Preservation Across Handoffs](#10-context-preservation-across-handoffs)
11. [Per-Agent Plugin Overrides](#11-per-agent-plugin-overrides)
12. [Pipeline Nodes — Guardrails](#12-pipeline-nodes--guardrails)
13. [Turn Detection & Input Control](#13-turn-detection--input-control)
14. [Session Events & Callbacks](#14-session-events--callbacks)
15. [Tasks — Structured Data Collection](#15-tasks--structured-data-collection)
16. [Task Groups — Ordered Multi-Step Flows](#16-task-groups--ordered-multi-step-flows)
17. [Background Audio](#17-background-audio)
18. [Runtime Agent Updates](#18-runtime-agent-updates)
19. [Error Handling & Recovery](#19-error-handling--recovery)
20. [Session Shutdown & Cleanup](#20-session-shutdown--cleanup)
21. [Advanced Patterns](#21-advanced-patterns)
22. [Decision Matrix](#22-decision-matrix)

---

## 1. Agent Greeting & Initial Speech

**Complexity: Trivial**
The simplest agent action — producing a greeting when the agent becomes active.

### 1.1 — Fixed Text Greeting

```python
class MyAgent(Agent):
    async def on_enter(self) -> None:
        await self.session.say("Hello, how can I help you today?")
```

Non-interruptible variant:

```python
await self.session.say(
    "Hello, how can I help you today?",
    allow_interruptions=False,
)
```

### 1.2 — LLM-Generated Greeting (from instructions)

The LLM generates the greeting based on the agent's `instructions`:

```python
class MyAgent(Agent):
    def __init__(self):
        super().__init__(instructions="You are a friendly concierge.")

    async def on_enter(self) -> None:
        self.session.generate_reply()
```

### 1.3 — LLM-Generated Greeting (with explicit prompt)

Override the generation with a one-shot instruction:

```python
async def on_enter(self) -> None:
    await self.session.generate_reply(
        instructions="Greet the user warmly and ask how you can help.",
    )
```

### 1.4 — Personalized Greeting (from userdata)

Access session-level state to personalize:

```python
async def on_enter(self) -> None:
    userdata: SessionInfo = self.session.userdata
    await self.session.generate_reply(
        instructions=f"Greet {userdata.user_name} by name and offer assistance.",
    )
```

### 1.5 — Greeting with Pre-Synthesized Audio

Bypass TTS entirely by providing pre-rendered audio frames:

```python
from livekit.agents.utils.audio import audio_frames_from_file

async def on_enter(self) -> None:
    await self.session.say(
        "Welcome to our service.",
        audio=audio_frames_from_file("greeting.ogg"),
    )
```

---

## 2. Agent Lifecycle Hooks

**Complexity: Simple**
Methods on `Agent` (and `AgentTask`) that fire at defined points in the lifecycle.

### 2.1 — `on_enter`

Called when the agent becomes the active agent in the session (first agent or after handoff).

```python
class MyAgent(Agent):
    async def on_enter(self) -> None:
        self.session.generate_reply()
```

**When it fires:**
- Session starts with this agent via `session.start(agent=...)`
- Another agent hands off to this agent (tool return or `session.update_agent`)

**Can return:** `None` or an `AgentTask` (to immediately start a task).

### 2.2 — `on_exit`

Called **before** this agent gives control to another agent. Used for:
- Goodbye messages
- State cleanup / persistence
- Summary generation

```python
class MyAgent(Agent):
    async def on_exit(self) -> None:
        await self.session.generate_reply(
            instructions="Tell the user a friendly goodbye before you exit.",
        )
```

### 2.3 — `on_user_turn_completed`

Called after the user finishes speaking and before the LLM generates a reply.
The most versatile hook — used for input guardrails, RAG injection, and turn manipulation.

```python
class MyAgent(Agent):
    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage,
    ) -> None:
        # Runs before LLM reply generation
        pass
```

**Parameters:**
- `turn_ctx: ChatContext` — the conversation context that will be sent to the LLM
- `new_message: ChatMessage` — the user's transcribed message (mutable)

**Common patterns:**

| Pattern | Implementation |
|---------|---------------|
| Block empty turns | `if not new_message.text_content: raise StopResponse()` |
| Input sanitization | Modify `new_message.content` |
| RAG injection | `turn_ctx.add_message(role="assistant", content=rag_result)` |
| Fast pre-response | `self.session.say(filler, add_to_chat_ctx=False)` |
| Prompt injection guard | Check for known attack patterns, rewrite or raise `StopResponse` |

---

## 3. Speech & Audio Control

**Complexity: Simple**

### 3.1 — `session.say()` — Predefined Text

```python
handle = session.say("Processing your request...")
await handle                          # wait for playout
```

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | `str` | — | Text to synthesize |
| `allow_interruptions` | `bool` | `True` | Whether user can interrupt |
| `add_to_chat_ctx` | `bool` | `True` | Add to conversation history |
| `audio` | `AsyncIterable[AudioFrame]` | `None` | Pre-rendered audio (bypasses TTS) |

### 3.2 — `session.generate_reply()` — LLM-Driven

```python
# One-shot instruction (not added to chat history)
session.generate_reply(instructions="Summarize the conversation so far.")

# Simulate user input (added to chat history)
session.generate_reply(user_input="What's the weather today?")

# Control tool usage
session.generate_reply(tool_choice="none")          # no tools
session.generate_reply(tool_choice="auto")          # default
session.generate_reply(tool_choice="required")      # force tool call

# Non-interruptible reply
await session.generate_reply(
    instructions="Read the terms of service.",
    allow_interruptions=False,
)
```

### 3.3 — `session.interrupt()`

Programmatically stop the agent's current speech:

```python
self.session.interrupt()
# or from a SpeechHandle
handle = session.say("long text...")
handle.interrupt()
```

When interrupted, conversation history is truncated to only include the speech the user actually heard.

### 3.4 — SpeechHandle Inspection

```python
handle = session.say("Hello")

handle.interrupted            # bool — was it interrupted?
handle.done()                 # bool — is playout finished?
await handle.wait_for_playout()

handle.add_done_callback(lambda _: print("speech finished"))
```

---

## 4. Instructions & Persona

**Complexity: Simple**

### 4.1 — Static Instructions

```python
Agent(instructions="You are a customer service agent for Acme Corp.")
```

### 4.2 — Structured Instructions with Guardrails

```python
Agent(instructions="""You are a customer service assistant.

## Guardrails
- NEVER discuss competitor products.
- NEVER share internal pricing formulas.
- If the user is abusive, end the conversation professionally.
- ALWAYS verify user identity before sharing account details.
""")
```

### 4.3 — Dynamic Instructions at Runtime

```python
await agent.update_instructions("New instructions with updated context.")
```

### 4.4 — Per-Turn Instruction Override

```python
session.generate_reply(instructions="For this response only, be extra concise.")
```

This instruction is ephemeral — it does not persist in the agent's `instructions` field.

---

## 5. Tools — Function Tools

**Complexity: Moderate**

### 5.1 — Decorator on Agent Class

```python
class MyAgent(Agent):
    @function_tool()
    async def lookup_weather(self, context: RunContext, location: str) -> dict:
        """Look up weather information.

        Args:
            location: City name to look up.
        """
        return {"weather": "sunny", "temperature_f": 70}
```

The docstring becomes the tool description for the LLM. `Args:` section maps to parameter descriptions.

### 5.2 — Standalone Tool (Shared Across Agents)

```python
@function_tool()
async def lookup_user(context: RunContext, user_id: str) -> dict:
    """Look up user by ID."""
    return {"name": "John"}

class AgentA(Agent):
    def __init__(self):
        super().__init__(tools=[lookup_user])

class AgentB(Agent):
    def __init__(self):
        super().__init__(tools=[lookup_user])
```

### 5.3 — Programmatic (Dynamic) Tool Creation

Build tools at runtime from config, database, or external source:

```python
async def _get_course_info(info: CourseInfo) -> str:
    return f"Course: {info.course}"

agent = Agent(
    tools=[
        function_tool(
            _get_course_info,
            name="get_course_info",
            description="Get information about a course",
        )
    ]
)
```

### 5.4 — Dynamic Tools from Enum (Database-Driven)

```python
courses = await db.list_courses()
CourseType = Enum("CourseType", {c.replace(" ", "_"): c for c in courses})

class CourseInfo(BaseModel):
    course: CourseType
    location: Literal["online", "in-person"]
```

Pydantic `Field` with `json_schema_extra={"enum": [...]}` also works for constraining parameters.

### 5.5 — Raw JSON Schema Tool

```python
raw_schema = {
    "type": "function",
    "name": "get_weather",
    "parameters": {
        "type": "object",
        "properties": {"location": {"type": "string"}},
        "required": ["location"],
    },
}

@function_tool(raw_schema=raw_schema)
async def get_weather(raw_arguments: dict[str, object], context: RunContext):
    return f"Weather in {raw_arguments['location']} is sunny"
```

### 5.6 — Tool Error Handling

```python
from livekit.agents import ToolError

@function_tool()
async def book_slot(self, context: RunContext, slot_id: str):
    """Book a time slot."""
    if not is_available(slot_id):
        raise ToolError("This slot is no longer available.")
    return "Booked."
```

`ToolError` message is sent to the LLM as the tool result. Other exceptions become a generic "An internal error occurred" message.

### 5.7 — Speech Inside Tools (User Feedback)

```python
@function_tool()
async def process_order(self, context: RunContext, order_id: str):
    """Process an order."""
    self.session.generate_reply(
        instructions=f"Tell the user you're processing order {order_id}."
    )
    await context.wait_for_playout()
    result = await heavy_processing(order_id)
    return result
```

### 5.8 — Frontend RPC Tool

Call frontend code from the agent:

```python
@function_tool()
async def get_user_location(context: RunContext, high_accuracy: bool):
    """Get the user's location from the frontend."""
    room = get_job_context().room
    participant = next(iter(room.remote_participants))
    response = await room.local_participant.perform_rpc(
        destination_identity=participant,
        method="getUserLocation",
        payload=json.dumps({"highAccuracy": high_accuracy}),
        response_timeout=10.0,
    )
    return response
```

---

## 6. Tool Interruption & Speech Control

**Complexity: Moderate**

### 6.1 — Disallow Interruptions (Critical Operations)

```python
@function_tool()
async def process_payment(self, context: RunContext, amount: float):
    """Process payment — cannot be interrupted."""
    context.disallow_interruptions()
    await charge_card(amount)
    return "Payment processed."
```

### 6.2 — Long-Running Tool with Interruption Detection

```python
@function_tool()
async def search_web(self, query: str, run_ctx: RunContext) -> str | None:
    """Search the web."""
    future = asyncio.ensure_future(self._heavy_search(query))
    await run_ctx.speech_handle.wait_if_not_interrupted([future])

    if run_ctx.speech_handle.interrupted:
        future.cancel()
        return None     # discarded — tool no longer exists from LLM perspective

    return future.result()
```

**Key insight:** When a tool is interrupted, it's removed from the chat history entirely. Returning `None` from an interrupted tool is safe.

### 6.3 — Cached TTS Hold Message

Pre-synthesize a hold message to avoid TTS latency:

```python
HOLD_FRAMES: list[rtc.AudioFrame] = []

async def preload_hold_message(tts) -> None:
    async for event in tts.synthesize("Let me check that for you."):
        HOLD_FRAMES.append(event.frame)

@function_tool()
async def check_status(self, context: RunContext, order_id: str) -> str:
    """Check order status."""
    hold = context.session.say(
        "Let me check that for you.",
        audio=(frame for frame in HOLD_FRAMES),
        add_to_chat_ctx=False,
    )
    result = await fetch_order_status(order_id)
    if not hold.interrupted and not hold.done():
        hold.interrupt()
    return result
```

---

## 7. Dynamic Tool Management

**Complexity: Moderate**

### 7.1 — Update Tools After Agent Creation

```python
await agent.update_tools(
    agent.tools + [new_tool]                    # add
)
await agent.update_tools(
    agent.tools - [old_tool]                    # remove
)
await agent.update_tools([tool_a, tool_b])      # replace all
```

### 7.2 — Temporal Tools via `llm_node` Override

Add tools only for the current LLM call (not persisted):

```python
class MyAgent(Agent):
    async def llm_node(self, chat_ctx, tools, model_settings):
        async def _get_weather(location: str) -> str:
            return f"Weather in {location} is sunny."

        tools.append(
            function_tool(
                _get_weather,
                name="get_weather",
                description="Get the weather",
            )
        )
        return Agent.default.llm_node(self, chat_ctx, tools, model_settings)
```

### 7.3 — Session-Level Tools (All Agents Share)

```python
session = AgentSession(
    tools=[shared_tool_a, shared_tool_b],
)
```

---

## 8. State Management — Userdata

**Complexity: Moderate**

### 8.1 — Define Session State

```python
@dataclass
class SessionInfo:
    user_name: str | None = None
    order_items: list[str] = field(default_factory=list)
    verified: bool = False
```

### 8.2 — Attach to Session

```python
session = AgentSession[SessionInfo](
    userdata=SessionInfo(),
)
```

### 8.3 — Access from Agent

```python
class MyAgent(Agent):
    async def on_enter(self) -> None:
        ud: SessionInfo = self.session.userdata
        if ud.user_name:
            await self.session.generate_reply(
                instructions=f"Welcome back, {ud.user_name}."
            )
```

### 8.4 — Access from Tool via RunContext

```python
@function_tool()
async def record_name(context: RunContext[SessionInfo], name: str) -> str:
    """Record name."""
    context.userdata.user_name = name
    return f"Name set to {name}"
```

### 8.5 — State-Driven Conditional Logic

```python
@function_tool()
async def record_age(self, context: RunContext[SessionInfo], age: int):
    """Record age."""
    context.userdata.age = age
    if context.userdata.user_name and context.userdata.age:
        return ServiceAgent()     # handoff when all data collected
    return None                   # stay on current agent
```

### 8.6 — Complex State with Agent Registry

```python
@dataclass
class UserData:
    customer_name: str | None = None
    order: list[str] = field(default_factory=list)
    agents: dict[str, Agent] = field(default_factory=dict)
    prev_agent: Agent | None = None

# Pre-register all agents
userdata = UserData()
userdata.agents = {
    "greeter": Greeter(menu),
    "reservation": Reservation(),
    "takeaway": Takeaway(menu),
}

# Transfer by name
async def _transfer_to_agent(self, name: str, context: RunContext) -> tuple[Agent, str]:
    userdata = context.userdata
    userdata.prev_agent = context.session.current_agent
    return userdata.agents[name], f"Transferring to {name}."
```

### 8.7 — State Summarization for Context Injection

```python
@dataclass
class UserData:
    customer_name: str | None = None
    order: list[str] = field(default_factory=list)

    def summarize(self) -> str:
        return yaml.dump({
            "customer_name": self.customer_name or "unknown",
            "order": self.order or "none",
        })
```

Used in `on_enter` to inject current state into the LLM context:

```python
async def on_enter(self) -> None:
    chat_ctx = self.chat_ctx.copy()
    chat_ctx.add_message(
        role="system",
        content=f"Current user data: {self.session.userdata.summarize()}",
    )
    await self.update_chat_ctx(chat_ctx)
    self.session.generate_reply(tool_choice="none")
```

---

## 9. Handoffs — Multi-Agent Routing

**Complexity: Moderate–High**

### 9.1 — Basic Handoff via Tool Return

Return an `Agent` instance from a `@function_tool` to trigger a handoff:

```python
@function_tool()
async def route_to_billing(self, context: RunContext):
    """Transfer to billing specialist."""
    return BillingAgent()
```

### 9.2 — Handoff with Message

The message is passed to the LLM as the tool result before the handoff:

```python
return BillingAgent(), "Transferring you to our billing department."
```

### 9.3 — Handoff with Chat History

```python
return BillingAgent(chat_ctx=self.chat_ctx)
```

**Variants:**

| Expression | Behavior |
|------------|----------|
| `return NewAgent()` | Fresh context — agent starts clean |
| `return NewAgent(chat_ctx=self.chat_ctx)` | Carries full conversation history |
| `return agent, "message"` | Handoff + tool result message |
| `return None` | No handoff — stay on current agent |

### 9.4 — Programmatic Agent Swap (No Tool)

```python
session.update_agent(NewAgent())
```

Bypasses tool execution — useful for event-driven transitions.

### 9.5 — Conditional Handoff

```python
@function_tool()
async def confirm_checkout(self, context: RunContext) -> str | tuple[Agent, str]:
    """Confirm the checkout."""
    if not context.userdata.order:
        return "No order found. Please make an order first."    # tool result, no handoff
    return CheckoutAgent(), "Proceeding to checkout."            # handoff
```

### 9.6 — Registry-Based Transfer

Pre-instantiated agents stored in userdata for reuse:

```python
async def _transfer_to_agent(self, name: str, context: RunContext) -> tuple[Agent, str]:
    userdata = context.userdata
    userdata.prev_agent = context.session.current_agent
    next_agent = userdata.agents[name]
    return next_agent, f"Transferring to {name}."
```

### 9.7 — Multi-Agent with State-Driven Routing

Agent swaps triggered by state changes in `RunContext`:

```python
class NarratorAgent(Agent):
    @function_tool()
    async def initiate_combat(self, context: RunContext, enemies: list[str]):
        """Start combat."""
        context.userdata.combat_state = Combat.initialize(enemies)
        return CombatAgent()

class CombatAgent(Agent):
    @function_tool()
    async def end_combat(self, context: RunContext, victory: bool):
        """End combat."""
        context.userdata.combat_state = None
        return NarratorAgent()
```

---

## 10. Context Preservation Across Handoffs

**Complexity: Moderate**

### 10.1 — Full History

```python
return NewAgent(chat_ctx=self.chat_ctx)
```

### 10.2 — Truncated History (from previous agent)

Useful for large conversations — keeps only the last N items:

```python
async def on_enter(self) -> None:
    chat_ctx = self.chat_ctx.copy()
    if isinstance(self.session.userdata.prev_agent, Agent):
        truncated = self.session.userdata.prev_agent.chat_ctx.copy(
            exclude_instructions=True,
            exclude_function_call=False,
            exclude_handoff=True,
            exclude_config_update=True,
        ).truncate(max_items=6)

        existing_ids = {item.id for item in chat_ctx.items}
        new_items = [i for i in truncated.items if i.id not in existing_ids]
        chat_ctx.items.extend(new_items)

    await self.update_chat_ctx(chat_ctx)
```

### 10.3 — Session History (Global)

Full history is always available regardless of handoffs:

```python
session.history          # all items across all agents
session.history.items    # list of ChatItem
```

---

## 11. Per-Agent Plugin Overrides

**Complexity: Moderate**

Each agent can override the session's default STT, LLM, TTS, and VAD:

```python
class ManagerAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions="You are a manager.",
            llm="openai/gpt-4.1",                  # more capable model
            tts=inference.TTS(
                model="cartesia/sonic-3",
                voice="manager-voice-id",           # different voice
            ),
        )
```

**Override scope:**

| Parameter | Session default | Agent override |
|-----------|----------------|----------------|
| `stt` | All agents | Per-agent ears |
| `llm` | All agents | Per-agent brain |
| `tts` | All agents | Per-agent voice |
| `vad` | All agents | Per-agent VAD |
| `turn_detection` | All agents | Per-agent turn model |
| `allow_interruptions` | All agents | Per-agent interruption policy |
| `min_endpointing_delay` | All agents | Per-agent silence tolerance |
| `max_endpointing_delay` | All agents | Per-agent max wait |

**Realtime model override (mixed pipelines):**

```python
class StoryAgent(Agent):
    def __init__(self, name: str, location: str, *, chat_ctx=None):
        super().__init__(
            instructions=f"Tell a story for {name} from {location}.",
            llm=openai.realtime.RealtimeModel(voice="echo"),
            tts=None,               # disable TTS — realtime model produces audio directly
            chat_ctx=chat_ctx,
        )
```

---

## 12. Pipeline Nodes — Guardrails

**Complexity: High**

Pipeline node overrides intercept data flowing through the VAD → STT → LLM → TTS pipeline.

### 12.1 — `stt_node` — Audio Preprocessing / Transcript Filter

```python
async def stt_node(self, audio, model_settings):
    """Post-process transcription before it reaches the LLM."""
    async for event in Agent.default.stt_node(self, audio, model_settings):
        yield event
```

### 12.2 — `llm_node` — Output Guardrail / Content Moderation

The most powerful node — full control over the LLM call:

```python
async def llm_node(self, chat_ctx, tools, model_settings):
    """Custom LLM processing with moderation."""
    async def process_stream():
        buffer = ""
        async with self.session.llm.chat(chat_ctx=chat_ctx, tools=tools) as stream:
            async for chunk in stream:
                content = getattr(chunk.delta, "content", None)
                if content:
                    buffer += content
                    if await is_safe(buffer):
                        yield chunk
                    else:
                        yield "I can't respond to that."
                        return
    return process_stream()
```

**Default behavior access:**

```python
return Agent.default.llm_node(self, chat_ctx, tools, model_settings)
```

### 12.3 — `tts_node` — Speech Output Filter

```python
async def tts_node(self, text, model_settings):
    """Replace competitor names in speech output."""
    async def filtered():
        async for chunk in text:
            yield chunk.replace("CompetitorX", "another provider")

    async for frame in Agent.default.tts_node(self, filtered(), model_settings):
        yield frame
```

### 12.4 — `transcription_node` — Transcript Cleanup

Clean text before the user sees the transcript:

```python
async def transcription_node(self, text, model_settings):
    """Remove unwanted characters from visible transcript."""
    async for delta in text:
        yield delta.replace("😘", "")
```

### 12.5 — Input Guardrail via `on_user_turn_completed`

```python
async def on_user_turn_completed(self, turn_ctx, new_message):
    user_text = new_message.text_content or ""

    # Prompt injection guard
    if any(p in user_text.lower() for p in ["ignore previous", "system prompt"]):
        new_message.content = ["I can't process that request."]
        return

    # PII redaction
    import re
    new_message.content = [
        re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED-SSN]", user_text)
    ]
```

### 12.6 — Abort Reply Entirely

```python
async def on_user_turn_completed(self, turn_ctx, new_message):
    if not new_message.text_content:
        raise StopResponse()
```

### Guardrail Summary

| Type | Where | How |
|------|-------|-----|
| Input validation | `on_user_turn_completed` | Modify / block `new_message` |
| Abort reply | `on_user_turn_completed` | `raise StopResponse()` |
| Output filter | `llm_node` override | Buffer + moderate before forwarding |
| Audio preprocess | `stt_node` override | Filter audio or transcript |
| TTS postprocess | `tts_node` override | Modify text before synthesis |
| Transcript clean | `transcription_node` override | Clean text before user sees it |
| Behavioral | Agent `instructions` | Prompt engineering |

---

## 13. Turn Detection & Input Control

**Complexity: Moderate**

### 13.1 — Turn Detection Modes

```python
# Model-based (recommended)
session = AgentSession(
    turn_detection=MultilingualModel(),
    vad=silero.VAD.load(),
)

# VAD only
session = AgentSession(turn_detection="vad", vad=silero.VAD.load())

# STT endpointing
session = AgentSession(turn_detection="stt", stt=stt_instance, vad=silero.VAD.load())

# Manual (push-to-talk)
session = AgentSession(turn_detection="manual")
```

### 13.2 — Push-to-Talk Pattern

```python
session = AgentSession(turn_detection="manual")
session.input.set_audio_enabled(False)

@room.local_participant.register_rpc_method("start_turn")
async def start_turn(data: rtc.RpcInvocationData):
    session.interrupt()
    session.clear_user_turn()
    session.room_io.set_participant(data.caller_identity)
    session.input.set_audio_enabled(True)

@room.local_participant.register_rpc_method("end_turn")
async def end_turn(data: rtc.RpcInvocationData):
    session.input.set_audio_enabled(False)
    user_transcript = await session.commit_user_turn(
        transcript_timeout=5.0,
        stt_flush_duration=2.0,
    )

@room.local_participant.register_rpc_method("cancel_turn")
async def cancel_turn(data: rtc.RpcInvocationData):
    session.input.set_audio_enabled(False)
    session.clear_user_turn()
```

### 13.3 — Interruption Configuration

```python
session = AgentSession(
    allow_interruptions=True,
    min_interruption_words=0,               # min words before interruption triggers
    min_interruption_duration=0.5,          # min speech duration before interruption
    false_interruption_timeout=2.0,         # timeout before "false interruption" signal
    resume_false_interruption=True,         # resume speech after false interruption
    aec_warmup_duration=3.0,               # block interruptions during AEC warmup
    discard_audio_if_uninterruptible=True,
)
```

### 13.4 — Preemptive Generation

Start LLM response before end-of-turn is confirmed:

```python
session = AgentSession(preemptive_generation=True)
```

### 13.5 — User Away Detection

```python
session = AgentSession(user_away_timeout=12.5)

@session.on("user_state_changed")
def _user_state_changed(ev: UserStateChangedEvent):
    if ev.new_state == "away":
        asyncio.create_task(check_user_presence())
```

---

## 14. Session Events & Callbacks

**Complexity: Moderate**

### 14.1 — Agent State Changes

```python
@session.on("agent_state_changed")
def on_agent_state(ev: AgentStateChangedEvent):
    # States: "initializing" | "idle" | "listening" | "thinking" | "speaking"
    logger.info(f"Agent → {ev.new_state}")
```

### 14.2 — User State Changes

```python
@session.on("user_state_changed")
def on_user_state(ev: UserStateChangedEvent):
    # States: "speaking" | "listening" | "away"
    if ev.new_state == "away":
        asyncio.create_task(handle_user_away())
```

### 14.3 — User Input Transcription

```python
@session.on("user_input_transcribed")
def on_transcript(ev):
    logger.info(f"User said: {ev.transcript}")
```

### 14.4 — Conversation Item Added

```python
@session.on("conversation_item_added")
def on_item(ev):
    logger.info(f"New item: {ev.item}")
```

### 14.5 — Metrics Collection

```python
usage_collector = metrics.UsageCollector()

@session.on("metrics_collected")
def _on_metrics(ev: MetricsCollectedEvent):
    metrics.log_metrics(ev.metrics)
    usage_collector.collect(ev.metrics)
```

### 14.6 — Session Close

```python
@session.on("close")
def on_close(ev: CloseEvent):
    print(f"Session closed, reason: {ev.reason}")
    for item in session.history.items:
        match item.type:
            case "message":
                print(f"{item.role}: {item.text_content}")
            case "function_call":
                print(f"Tool call: {item.name}({item.arguments})")
            case "function_call_output":
                print(f"Tool result: {item.output}")
            case "agent_handoff":
                print(f"Handoff: {item.old_agent_id} → {item.new_agent_id}")
```

### 14.7 — Error Events

```python
@session.on("error")
def on_error(ev: ErrorEvent):
    if ev.error.recoverable:
        return

    # Bypass TTS with pre-rendered audio
    session.say(
        "I'm having trouble. Let me transfer your call.",
        audio=audio_frames_from_file("error_message.ogg"),
        allow_interruptions=False,
    )

    # Mark as recoverable to continue
    # ev.error.recoverable = True
```

### 14.8 — Function Tools Executed

```python
@session.on("function_tools_executed")
def _on_tools_executed(ev):
    logger.info(f"Tools executed: {ev}")
```

### 14.9 — Shutdown Callbacks

```python
async def log_usage():
    summary = usage_collector.get_summary()
    logger.info(f"Usage: {summary}")

ctx.add_shutdown_callback(log_usage)
```

### 14.10 — Session End Report

```python
async def on_session_end(ctx: JobContext) -> None:
    report = ctx.make_session_report()
    data = json.dumps(report.to_dict(), indent=2)
    await save_report(data)

@server.rtc_session(on_session_end=on_session_end)
async def entrypoint(ctx: JobContext): ...
```

---

## 15. Tasks — Structured Data Collection

**Complexity: High**

`AgentTask[T]` is a focused agent that runs to completion and returns a typed result.

### 15.1 — Basic Task

```python
class CollectConsent(AgentTask[bool]):
    def __init__(self):
        super().__init__(instructions="Ask for recording consent.")

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="Ask permission to record the call."
        )

    @function_tool()
    async def consent_given(self) -> None:
        """User gives consent."""
        self.complete(True)

    @function_tool()
    async def consent_denied(self) -> None:
        """User denies consent."""
        self.complete(False)
```

### 15.2 — Using a Task from an Agent

```python
class MainAgent(Agent):
    async def on_enter(self) -> None:
        consent = await CollectConsent(chat_ctx=self.chat_ctx)
        if consent:
            await self.session.generate_reply(instructions="Offer assistance.")
```

Tasks are `await`-able — they block until `self.complete(result)` is called.

### 15.3 — Multi-Field Data Collection Task

```python
@dataclass
class ContactInfo:
    name: str
    email: str
    phone: str

class GetContactTask(AgentTask[ContactInfo]):
    def __init__(self):
        super().__init__(instructions="Collect name, email, and phone.")
        self._data: dict = {}

    @function_tool()
    async def record_name(self, name: str):
        """Record name."""
        self._data["name"] = name
        self._check()

    @function_tool()
    async def record_email(self, email: str):
        """Record email."""
        self._data["email"] = email
        self._check()

    @function_tool()
    async def record_phone(self, phone: str):
        """Record phone."""
        self._data["phone"] = phone
        self._check()

    def _check(self):
        if len(self._data) == 3:
            self.complete(ContactInfo(**self._data))
        else:
            self.session.generate_reply(
                instructions="Continue collecting remaining info."
            )
```

### 15.4 — Built-in Tasks

```python
from livekit.agents.beta.workflows import GetEmailTask, GetDtmfTask

# Email collection
email_result = await GetEmailTask(
    chat_ctx=self.chat_ctx,
    extra_instructions="Be polite.",
)
# email_result.email_address

# DTMF digit collection
dtmf_result = await GetDtmfTask(
    num_digits=4,
    ask_for_confirmation=True,
    extra_instructions="Ask for their PIN.",
)
# dtmf_result.user_input
```

### 15.5 — Task with Disqualification

```python
@function_tool()
async def disqualify(context: RunContext, reason: str) -> None:
    """Disqualify and terminate."""
    context.session.generate_reply(
        instructions=f"Inform them the reason was: {reason}."
    )
    context.session.shutdown()
```

---

## 16. Task Groups — Ordered Multi-Step Flows

**Complexity: High**

`TaskGroup` orchestrates multiple tasks in sequence with regression support.

### 16.1 — Basic Task Group

```python
from livekit.agents.beta.workflows import TaskGroup

class SurveyAgent(Agent):
    async def on_enter(self) -> AgentTask:
        group = TaskGroup()
        group.add(lambda: IntroTask(), id="intro", description="Collect name")
        group.add(lambda: GetEmailTask(), id="email", description="Collect email")
        group.add(lambda: CommuteTask(), id="commute", description="Ask commute")
        group.add(lambda: ExperienceTask(), id="experience", description="Work history")
        group.add(lambda: BehavioralTask(), id="behavioral", description="Strengths/weaknesses")

        results = await group
        # results.task_results = {"intro": IntroResults(...), "email": ..., ...}
```

### 16.2 — Task Group Options

```python
TaskGroup(
    chat_ctx=self.chat_ctx,             # shared context
    summarize_chat_ctx=True,            # summarize when done (default True)
    return_exceptions=False,            # propagate exceptions (default False)
)
```

### 16.3 — Task Group Regression

Users can naturally go back to correct earlier answers. The task group handles this automatically.

### 16.4 — Accessing Results

```python
results = await group
for task_id, result in results.task_results.items():
    print(f"{task_id}: {result}")
```

---

## 17. Background Audio

**Complexity: Moderate**

### 17.1 — Ambient + Thinking Sounds

```python
from livekit.agents import BackgroundAudioPlayer, AudioConfig, BuiltinAudioClip

background_audio = BackgroundAudioPlayer(
    ambient_sound=AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=0.8),
    thinking_sound=[
        AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.8),
        AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.7),
    ],
)
await background_audio.start(room=ctx.room, agent_session=session)
```

### 17.2 — Custom Audio File

```python
ambient_sound=AudioConfig("path/to/bg_noise.mp3", volume=1.0)
```

### 17.3 — Play Audio On Demand

```python
background_audio.play("notification.ogg")
```

### 17.4 — Built-in Audio Clips

| Clip | Usage |
|------|-------|
| `BuiltinAudioClip.OFFICE_AMBIENCE` | Background ambient sound |
| `BuiltinAudioClip.KEYBOARD_TYPING` | Thinking indicator |
| `BuiltinAudioClip.KEYBOARD_TYPING2` | Thinking indicator (variant) |

---

## 18. Runtime Agent Updates

**Complexity: Moderate**

### 18.1 — Update Instructions

```python
await agent.update_instructions("Updated instructions for new context.")
```

### 18.2 — Update Tools

```python
await agent.update_tools(agent.tools + [new_tool])
await agent.update_tools(agent.tools - [old_tool])
await agent.update_tools([replacement_tool_set])
```

### 18.3 — Update Chat Context

```python
chat_ctx = agent.chat_ctx.copy()
chat_ctx.add_message(role="system", content="New context information.")
await agent.update_chat_ctx(chat_ctx)
```

### 18.4 — Swap Active Agent

```python
session.update_agent(NewAgent())
```

---

## 19. Error Handling & Recovery

**Complexity: High**

### 19.1 — Error Event Handling

```python
@session.on("error")
def on_error(ev: ErrorEvent):
    if ev.error.recoverable:
        return      # auto-recovered

    logger.error(f"Unrecoverable error: {ev.error}")

    # Fallback with pre-rendered audio
    session.say(
        "I'm having trouble right now.",
        audio=audio_frames_from_file("error_message.ogg"),
        allow_interruptions=False,
    )
```

### 19.2 — Mark Error as Recoverable

```python
@session.on("error")
def on_error(ev: ErrorEvent):
    # TTS and LLM are recreated per response — safe to recover
    if isinstance(ev.source, (tts.TTS, llm.LLM)):
        ev.error.recoverable = True
        return

    # STT stream persists — reset agent to recover
    if isinstance(ev.source, stt.STT):
        session.update_agent(session.current_agent)
        ev.error.recoverable = True
```

### 19.3 — Tool Errors

```python
raise ToolError("Slot not available.")
```

`ToolError` is communicated to the LLM as the tool result. Other exceptions produce a generic error.

### 19.4 — SIP Transfer on Fatal Error

```python
@session.on("close")
def on_close(_: CloseEvent):
    participant = next(
        p for p in ctx.room.remote_participants.values()
        if p.kind == ParticipantKind.PARTICIPANT_KIND_SIP
    )
    ctx.transfer_sip_participant(participant, "tel:+18003310500")
```

---

## 20. Session Shutdown & Cleanup

**Complexity: Moderate**

### 20.1 — Graceful Shutdown

```python
session.shutdown()
```

### 20.2 — Shutdown with Final Message

```python
await self.session.generate_reply(
    instructions="Say goodbye.",
    allow_interruptions=False,
)
self.session.shutdown()
```

### 20.3 — EndCallTool (Built-in)

```python
from livekit.agents.beta.tools import EndCallTool

Agent(
    tools=[
        EndCallTool(
            end_instructions="Thank the user and say goodbye.",
            delete_room=True,
        )
    ]
)
```

### 20.4 — Delete Room

```python
from livekit import api

job_ctx = get_job_context()
await job_ctx.api.room.delete_room(
    api.DeleteRoomRequest(room=job_ctx.room.name)
)
```

### 20.5 — Room Options for Auto-Cleanup

```python
room_options=room_io.RoomOptions(
    close_on_disconnect=True,
    delete_room_on_close=True,
)
```

---

## 21. Advanced Patterns

### 21.1 — Fast Pre-Response (Silence Filler)

Use a fast/cheap LLM to generate an instant acknowledgment while the main LLM processes:

```python
class PreResponseAgent(Agent):
    def __init__(self):
        super().__init__(instructions="You are a helpful assistant", llm=main_llm)
        self._fast_llm = groq.LLM(model="llama-3.1-8b-instant")

    async def on_user_turn_completed(self, turn_ctx, new_message):
        fast_ctx = turn_ctx.copy(
            exclude_instructions=True,
            exclude_function_call=True,
        ).truncate(max_items=3)
        fast_ctx.items.insert(0, ChatMessage(
            role="system",
            content=["Generate a 5-10 word filler response."],
        ))
        fast_ctx.items.append(new_message)

        self.session.say(
            self._fast_llm.chat(chat_ctx=fast_ctx).to_str_iterable(),
            add_to_chat_ctx=False,
        )
```

### 21.2 — RAG via `on_user_turn_completed`

Inject retrieved context before the LLM responds:

```python
async def on_user_turn_completed(self, turn_ctx, new_message):
    query = new_message.text_content
    rag_context = await vector_search(query)
    turn_ctx.add_message(role="assistant", content=f"Context: {rag_context}")
```

### 21.3 — Warm Transfer (SIP Escalation)

```python
from livekit.agents.beta.workflows import WarmTransferTask

result = await WarmTransferTask(
    target_phone_number="+15005006000",
    sip_trunk_id="ST_abcxyz",
    sip_number="+12003004000",
    chat_ctx=self.chat_ctx,
    extra_instructions="Summarize the conversation for the supervisor.",
)
# result.human_agent_identity
```

### 21.4 — IVR Navigation with DTMF

```python
from livekit.agents.beta.workflows.dtmf_inputs import GetDtmfTask

result = await GetDtmfTask(
    num_digits=8,
    ask_for_confirmation=False,
    extra_instructions="Ask for 8-digit customer ID.",
)
customer_id = result.user_input.replace(" ", "")
```

### 21.5 — Menu-Driven Navigation (IVR Pattern)

```python
async def run_menu(agent, *, prompt, options) -> str:
    normalized = dict(options.items())
    while True:
        instructions_text = f"{prompt} " + " ".join(
            f"Press {digit} for {label}." for digit, label in normalized.items()
        )
        result = await GetDtmfTask(
            num_digits=1,
            ask_for_confirmation=False,
            extra_instructions=instructions_text,
        )
        if result.user_input in normalized:
            return result.user_input
        agent.session.say("Invalid selection. Let's try again.")
```

### 21.6 — Inactive User Handling

```python
session = AgentSession(user_away_timeout=12.5)

inactivity_task: asyncio.Task | None = None

async def user_presence_task():
    for _ in range(3):
        await session.generate_reply(
            instructions="Check if the user is still there."
        )
        await asyncio.sleep(10)
    session.shutdown()

@session.on("user_state_changed")
def _user_state_changed(ev: UserStateChangedEvent):
    nonlocal inactivity_task
    if ev.new_state == "away":
        inactivity_task = asyncio.create_task(user_presence_task())
    elif inactivity_task is not None:
        inactivity_task.cancel()
```

### 21.7 — State-Reactive Agent (Background Callback Pattern)

An agent that changes course when background state changes:

```python
@dataclass
class SessionState:
    search_complete: bool = False
    search_result: str | None = None

class ReactiveAgent(Agent):
    async def on_enter(self) -> None:
        # Launch background task
        asyncio.create_task(self._background_search())
        self.session.generate_reply()

    async def _background_search(self):
        result = await expensive_search()
        self.session.userdata.search_complete = True
        self.session.userdata.search_result = result
        # Inject result into chat and trigger new reply
        chat_ctx = self.chat_ctx.copy()
        chat_ctx.add_message(
            role="system",
            content=f"Background search completed: {result}",
        )
        await self.update_chat_ctx(chat_ctx)
        self.session.generate_reply(
            instructions="The search results are now available. Share them."
        )
```

### 21.8 — Prewarm (Resource Preloading)

```python
def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

server.setup_fnc = prewarm

@server.rtc_session()
async def entrypoint(ctx: JobContext):
    vad = ctx.proc.userdata["vad"]
    session = AgentSession(vad=vad)
```

### 21.9 — Named Agent Dispatch

```python
@server.rtc_session(agent_name="billing-agent")
async def billing_entrypoint(ctx: JobContext):
    # Only dispatched when explicitly requested by name
    ...

@server.rtc_session(agent_name="support-agent")
async def support_entrypoint(ctx: JobContext):
    ...
```

### 21.10 — Participant Entrypoints

Run tasks per-participant rather than per-room:

```python
async def participant_task(ctx: JobContext, p: rtc.RemoteParticipant):
    logger.info(f"Task for {p.identity}")
    await asyncio.sleep(60)

ctx.add_participant_entrypoint(entrypoint_fnc=participant_task)
await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)
```

### 21.11 — MCP Server Integration

```python
from livekit.agents import mcp

# Remote HTTP server
mcp.MCPServerHTTP(
    url="https://api.example.com/mcp",
    allowed_tools=["search", "create"],
    headers={"Authorization": "Bearer token"},
)

# Local stdio process
mcp.MCPServerStdio(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
)
```

Attach to session (shared) or to specific agents.

### 21.12 — Initial Context from Job Metadata

```python
@server.rtc_session()
async def entrypoint(ctx: JobContext):
    metadata = json.loads(ctx.job.metadata)
    initial_ctx = ChatContext()
    initial_ctx.add_message(
        role="assistant",
        content=f"The user's name is {metadata['user_name']}.",
    )
    session = AgentSession(...)
    await session.start(agent=MyAgent(chat_ctx=initial_ctx), room=ctx.room)
```

### 21.13 — E2EE (End-to-End Encryption)

```python
e2ee_config = rtc.E2EEOptions(
    key_provider_options=rtc.KeyProviderOptions(shared_key=b"my_shared_key"),
    encryption_type=rtc.EncryptionType.GCM,
)
await ctx.connect(e2ee=e2ee_config)
```

---

## 22. Decision Matrix

| Need | Use |
|------|-----|
| Simple greeting | `on_enter` → `session.say()` or `session.generate_reply()` |
| Personalized greeting | `on_enter` → access `session.userdata` → `generate_reply(instructions=...)` |
| Distinct persona | Separate `Agent` subclass with own `instructions` |
| Different voice per agent | Agent-level `tts` override |
| Different model per agent | Agent-level `llm` override |
| External API call | `@function_tool` |
| External tool server | `MCPServerHTTP` / `MCPServerStdio` |
| Block bad input | `on_user_turn_completed` + modify message or `raise StopResponse()` |
| Filter LLM output | `llm_node` override |
| Modify speech output | `tts_node` override |
| Transfer conversation | Tool returning `Agent` instance |
| Programmatic transfer | `session.update_agent(NewAgent())` |
| Shared session state | `session.userdata` (dataclass) |
| Collect structured data | `AgentTask[T]` with `self.complete(result)` |
| Ordered multi-step flow | `TaskGroup` |
| User feedback during tools | `session.say()` / `session.generate_reply()` inside tool |
| Critical (non-interruptible) ops | `context.disallow_interruptions()` |
| Long-running tool | `speech_handle.wait_if_not_interrupted([future])` |
| Thinking sounds | `BackgroundAudioPlayer` with `thinking_sound` |
| Ambient background | `BackgroundAudioPlayer` with `ambient_sound` |
| Push-to-talk | `turn_detection="manual"` + RPC methods |
| Inactive user handling | `user_away_timeout` + `user_state_changed` event |
| Error recovery | `@session.on("error")` + `ev.error.recoverable = True` |
| Session reports | `on_session_end` callback + `ctx.make_session_report()` |
| SIP transfer | `ctx.transfer_sip_participant(participant, phone)` |
| Warm transfer | `WarmTransferTask(target_phone_number=..., ...)` |
| DTMF input | `GetDtmfTask(num_digits=..., ...)` |
| IVR menu | `GetDtmfTask` in a loop with option validation |
| RAG injection | `on_user_turn_completed` → `turn_ctx.add_message()` |
| Dynamic tools | `agent.update_tools()` or `llm_node` override |
| Preemptive generation | `AgentSession(preemptive_generation=True)` |
| State-reactive agent | Background task + `update_chat_ctx` + `generate_reply` |
| Context preservation | `NewAgent(chat_ctx=self.chat_ctx)` |
| Truncated context | `chat_ctx.copy(...).truncate(max_items=N)` |
| End call | `EndCallTool` or `session.shutdown()` |

---

## Architecture Overview

```
AgentServer
└── rtc_session (entrypoint)
    ├── prewarm (setup_fnc) — preload models
    ├── on_session_end — reports, cleanup
    └── AgentSession[T]
        ├── userdata: T — shared state across all agents
        ├── Events
        │   ├── agent_state_changed
        │   ├── user_state_changed
        │   ├── user_input_transcribed
        │   ├── conversation_item_added
        │   ├── metrics_collected
        │   ├── function_tools_executed
        │   ├── error
        │   └── close
        ├── Agent (active)
        │   ├── instructions — persona + guardrails
        │   ├── tools — @function_tool, standalone, dynamic
        │   ├── mcp_servers — HTTP, Stdio
        │   ├── Plugin overrides — stt, llm, tts, vad
        │   ├── Lifecycle hooks
        │   │   ├── on_enter — activation
        │   │   ├── on_exit — deactivation
        │   │   └── on_user_turn_completed — pre-reply
        │   ├── Pipeline nodes
        │   │   ├── stt_node — audio → text
        │   │   ├── llm_node — text → response
        │   │   ├── tts_node — text → audio
        │   │   └── transcription_node — text → visible transcript
        │   ├── Runtime updates
        │   │   ├── update_instructions()
        │   │   ├── update_tools()
        │   │   └── update_chat_ctx()
        │   └── Handoff — return Agent from tool
        ├── AgentTask[T] — structured data collection
        │   ├── on_enter
        │   ├── tools
        │   └── complete(result) — resolve awaitable
        ├── TaskGroup — ordered multi-task flow
        ├── BackgroundAudioPlayer
        │   ├── ambient_sound
        │   ├── thinking_sound
        │   └── play() — on-demand
        ├── Speech
        │   ├── say() — fixed text
        │   ├── generate_reply() — LLM-driven
        │   ├── interrupt() — stop speech
        │   └── SpeechHandle — inspect/await
        └── Input control
            ├── turn_detection — model, vad, stt, manual
            ├── set_audio_enabled()
            ├── commit_user_turn()
            └── clear_user_turn()
```
