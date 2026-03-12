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

---
---

# Part 2 — Dynamic Agent System Design

> Implementation strategy for building LiveKit agents on-the-fly from YAML configs.
> Maps each capability to: YAML schema, build-time mechanism, and LiveKit/Python tooling.

---

## Current State Summary

**What exists:**

| Component | Status | Location |
|-----------|--------|----------|
| `AgentConfig.handoffs: list[str]` | ✅ Schema exists | `models/config.py` |
| `AgentConfig.greeting: str` | ✅ Built as dynamic `on_enter` | `operations/build.py` |
| `AgentConfig.tools: list[str]` | ✅ Resolved from scanned modules | `operations/load.py` |
| `AgentConfig.mcp_servers: list[str]` | ✅ Resolved from YAML configs | `operations/build.py` |
| `Builder._bd_build_handoff()` | ✅ Creates `function_tool` per target | `operations/build.py` |
| `Builder._bd_agent_class()` | ✅ Dynamic subclass with `on_enter` | `operations/build.py` |
| `SessionState.data: dict[str, Any]` | ✅ Dynamic state keys from config | `models/state.py` |
| Handoff target validation | ❌ Missing — not checked in loader | — |
| Background task execution | ❌ Not implemented | — |
| Pre-response / filler | ❌ Not implemented | — |
| Task queue / priorities | ❌ Not implemented | — |
| Interruption / cancellation | ❌ Not implemented | — |
| State-reactive agent loop | ❌ Not implemented | — |

---

## F1. Handoff System — Validation & Build Order

### F1.1 — Current YAML (already works)

```yaml
# config/agents/assistant.yaml
name: assistant
instructions: |
  You are a helpful assistant.
greeting: Hello! How can I help?
tools:
  - web_search
handoffs:
  - web_scraper
  - researcher
```

Multiple handoffs per agent is fully supported — LiveKit treats each handoff as a
separate `@function_tool` that returns an `Agent`. The LLM sees N transfer tools and
chooses which one to call based on the conversation. **No change needed in schema.**

### F1.2 — Validation Gap (to implement in Loader)

**Problem:** If `assistant` declares `handoffs: [web_scraper]` but `web_scraper` is
not listed in `session.agents` or doesn't have a YAML config, the build will fail
silently or crash at runtime.

**Solution:** Add cross-reference validation in `Loader._ld_load_config()`:

```python
# In Loader._ld_load_config(), after loading agents and sessions:
for session_name, session_cfg in sessions.items():
    declared_agents = set(session_cfg.agents)
    for agent_name in session_cfg.agents:
        agent_cfg = agents.get(agent_name)
        if agent_cfg is None:
            raise ConfigLoadError(
                f"Session '{session_name}' references agent '{agent_name}' "
                f"but no config found. Available: {sorted(agents)}"
            )
        for target in agent_cfg.handoffs:
            if target not in declared_agents:
                raise ConfigLoadError(
                    f"Agent '{agent_name}' declares handoff to '{target}' "
                    f"but '{target}' is not in session '{session_name}' agents: {session_cfg.agents}"
                )
            if target not in agents:
                raise ConfigLoadError(
                    f"Agent '{agent_name}' declares handoff to '{target}' "
                    f"but no agent config found for '{target}'"
                )
```

**Where:** `operations/load.py` → `Loader._ld_load_config()`, after the three `for` loops.

### F1.3 — Build Order (Dependency Sorting)

**Problem:** When building agents, handoff tools reference target agents that must
also be buildable. Currently the builder creates agents on-demand inside the handoff
tool closure, so order doesn't strictly matter at build time. The closure captures
`builder` and `session_cfg` and calls `_bd_build_agent(target, ...)` at tool
invocation time (runtime).

**Current approach is correct** — handoff tools are closures that build target agents
lazily at handoff time. No topological sort needed. The validation in F1.2 ensures
all targets are valid at load time; the actual `Agent` instance is created at
runtime when the LLM triggers the handoff tool.

### F1.4 — Handoff with Context Preservation (current)

The current `_bd_build_handoff` already passes `chat_ctx`:

```python
@function_tool(name=f"transfer_to_{target}", description=description)
async def _transfer(context: RunContext[SessionState]) -> Agent:
    current_ctx = context.session.current_agent.chat_ctx if ... else NOT_GIVEN
    return builder._bd_build_agent(target, session_cfg, chat_ctx=current_ctx)
```

**Enhancement — configurable context mode per handoff:**

```yaml
# config/agents/assistant.yaml
handoffs:
  - target: web_scraper
    context: carry          # carry | fresh | truncated
    truncate_items: 6       # only if context: truncated
  - target: researcher
    context: fresh
```

This requires changing `AgentConfig.handoffs` from `list[str]` to
`list[str | HandoffConfig]` and adjusting `_bd_build_handoff`. See F1.5.

### F1.5 — HandoffConfig Model

```python
class HandoffConfig(BaseModelYAML):
    """Per-handoff configuration."""
    target: str
    context: Literal["carry", "fresh", "truncated"] = "carry"
    truncate_items: int = 6
    description: str | None = None    # override auto-generated description
```

In `AgentConfig`:

```python
handoffs: list[str | HandoffConfig] = Field(default_factory=list)

@model_validator(mode="after")
def _normalize_handoffs(self) -> AgentConfig:
    """Ensure handoffs is always list[HandoffConfig]."""
    self.handoffs = [
        HandoffConfig(target=h) if isinstance(h, str) else h
        for h in self.handoffs
    ]
    return self
```

**Build-time in `_bd_build_handoff`:**

```python
def _bd_build_handoff(self, handoff: HandoffConfig, session_cfg: SessionConfig) -> FunctionTool:
    target = handoff.target
    ctx_mode = handoff.context
    truncate = handoff.truncate_items
    # ...

    @function_tool(name=f"transfer_to_{target}", description=desc)
    async def _transfer(context: RunContext[SessionState]) -> Agent:
        match ctx_mode:
            case "carry":
                chat_ctx = context.session.current_agent.chat_ctx
            case "truncated":
                chat_ctx = context.session.current_agent.chat_ctx.copy(
                    exclude_instructions=True,
                    exclude_handoff=True,
                ).truncate(max_items=truncate)
            case "fresh":
                chat_ctx = NOT_GIVEN
        return builder._bd_build_agent(target, session_cfg, chat_ctx=chat_ctx)

    return _transfer
```

---

## F2. Background Task Execution

### F2.1 — Problem Statement

The front/assistant agent talks to the user. When the user requests something heavy
(web search, analysis, report generation), the agent should:

1. Acknowledge the request immediately (pre-response / filler)
2. Launch the task in background
3. Continue the conversation naturally
4. When the task completes, inject results into the conversation

### F2.2 — YAML Schema — Agent-Level Task Config

```yaml
# config/agents/assistant.yaml
name: assistant
instructions: |
  You are a helpful assistant. When launching background tasks,
  acknowledge the request and continue helping the user.
greeting: Hello! How can I help?

tools:
  - web_search

# NEW: background execution config
execution:
  mode: background            # background | blocking (default: blocking)
  pre_response:
    enabled: true
    message: "On it! Let me look that up. What else can I help with?"
    # OR use LLM-generated filler:
    # model: "fast"           # use a fast/cheap LLM for filler
    # prompt: "Generate a 5-10 word acknowledgment."
  on_complete:
    notify: true              # inject result into conversation when ready
    instructions: "The background task completed. Share the results naturally."
```

### F2.3 — Config Model

```python
class PreResponseConfig(BaseModelYAML):
    """Pre-response / filler message configuration."""
    enabled: bool = False
    message: str | None = None          # fixed text (takes priority)
    model: str | None = None            # fast LLM model string
    prompt: str = "Generate a brief acknowledgment in 5-10 words."

class OnCompleteConfig(BaseModelYAML):
    """Behavior when a background task completes."""
    notify: bool = True
    instructions: str = "Background task completed. Share the results with the user."

class ExecutionConfig(BaseModelYAML):
    """Controls how tools are executed — blocking vs background."""
    mode: Literal["background", "blocking"] = "blocking"
    pre_response: PreResponseConfig = Field(default_factory=PreResponseConfig)
    on_complete: OnCompleteConfig = Field(default_factory=OnCompleteConfig)
```

In `AgentConfig`:

```python
execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
```

### F2.4 — Build-Time Implementation

**Native LiveKit tools used:**
- `session.generate_reply(instructions=...)` — filler response
- `session.say(text, add_to_chat_ctx=False)` — non-history filler
- `asyncio.create_task()` — background execution
- `agent.update_chat_ctx()` — inject results into context
- `session.generate_reply()` — trigger LLM to present results

**Build-time in `_bd_agent_class`:**

When `execution.mode == "background"`, the dynamic Agent subclass wraps every tool
call in a background pattern. This is done by wrapping tools at build time for the
**launch**, and using two **complementary delivery mechanisms** for results.

#### Tool Wrapping — Launch Mechanism

Each tool that should run in background gets wrapped in a new function_tool that:
1. Fires a pre-response
2. Launches the real tool as `asyncio.create_task`
3. Registers the task in `SessionState` (or `TaskQueue`)
4. Returns immediately with an acknowledgment to the LLM

```python
def _bd_wrap_background_tool(
    self,
    tool: FunctionTool,
    exec_cfg: ExecutionConfig,
) -> FunctionTool:
    """Wrap a tool for background execution with pre-response and state tracking."""
    original_name = tool.info.name
    pre_cfg = exec_cfg.pre_response
    on_complete = exec_cfg.on_complete

    @function_tool(name=original_name, description=tool.info.description)
    async def _background_wrapper(context: RunContext[SessionState], **kwargs) -> str:
        state: SessionState = context.userdata
        task_id = f"{original_name}_{id(context)}"

        # 1. Pre-response
        if pre_cfg.enabled and pre_cfg.message:
            context.session.say(pre_cfg.message, add_to_chat_ctx=False)
        elif pre_cfg.enabled and pre_cfg.model:
            context.session.generate_reply(instructions=pre_cfg.prompt)

        # 2. Launch in background
        async def _run():
            try:
                result = await tool.execute(context, **kwargs)
                state.data[f"_task_{task_id}"] = {"status": "done", "result": result}
                # 3. Proactive notification (only when safe — see delivery mechanisms)
                if on_complete.notify:
                    _try_proactive_notify(context.session, task_id, original_name, result, on_complete)
            except asyncio.CancelledError:
                state.data[f"_task_{task_id}"] = {"status": "cancelled"}
            except Exception as exc:
                state.data[f"_task_{task_id}"] = {"status": "error", "error": str(exc)}

        task = asyncio.create_task(_run())
        state.data[f"_task_{task_id}"] = {"status": "running", "task": task}

        return f"Task '{original_name}' launched in background (id: {task_id}). Continuing conversation."

    return _background_wrapper
```

#### Result Delivery — Two Complementary Mechanisms

Results from background tasks need to reach the agent. Two mechanisms work
**together**, each covering the other's blind spot:

| Mechanism | When it fires | Pipeline-safe | Proactive | Latency |
|-----------|---------------|---------------|-----------|---------|
| **Primary: `on_user_turn_completed`** | User finishes speaking | Yes — runs between user input and LLM generation | No — requires user turn | Depends on user |
| **Secondary: Event-driven callback** | Task completes | Conditional — only safe when agent is idle | Yes — agent speaks unprompted | Immediate |

**Why `on_user_turn_completed` is the primary mechanism:**

LiveKit's internal pipeline is sequential: VAD → STT → `on_user_turn_completed` →
LLM → TTS. The hook runs at a **guaranteed safe point** — after user input is
transcribed but before the LLM generates a response. Injecting background results
here means:

- Zero race conditions with the pipeline
- Results are naturally woven into the LLM's next response
- No risk of corrupting `chat_ctx` mid-generation
- No risk of interrupting the user

**Why the event-driven callback is the secondary mechanism:**

If the user is silent (idle/listening), turn-based polling never fires, so results
pile up undelivered. The callback solves this by proactively notifying — but **only
when safe**:

```python
def _try_proactive_notify(
    session: AgentSession,
    task_id: str,
    name: str,
    result: str,
    on_complete: OnCompleteConfig,
) -> None:
    """Proactively notify the agent, but only if the pipeline is idle."""
    # Guard: only notify when the agent is NOT mid-pipeline
    # "listening" and "idle" mean no generation in flight
    if not hasattr(session, "agent_state") or session.agent_state not in ("idle", "listening"):
        return  # on_user_turn_completed will pick it up on the next turn

    agent = session.current_agent
    chat_ctx = agent.chat_ctx.copy()
    chat_ctx.add_message(
        role="system",
        content=f"<task_complete name='{name}'>{result}</task_complete>",
    )
    # These are fire-and-forget — safe because the pipeline is idle
    asyncio.create_task(agent.update_chat_ctx(chat_ctx))
    session.generate_reply(instructions=on_complete.instructions)
```

**What happens in each scenario:**

| Scenario | Primary (turn-based) | Secondary (event-driven) |
|----------|---------------------|-------------------------|
| User is talking, task completes | Next `on_user_turn_completed` picks up result | Skipped — agent not idle |
| User is silent, task completes | Waiting for user turn | Fires immediately — agent is idle |
| Multiple tasks complete between turns | All results injected at once in next turn | Each fires independently (if idle) |
| Task completes during LLM generation | Next turn picks it up | Skipped — agent is "thinking"/"speaking" |

**`on_user_turn_completed` (primary delivery — always active):**

```python
async def on_user_turn_completed(self, turn_ctx, new_message):
    state: SessionState = self.session.userdata
    completed = [
        (k, v) for k, v in state.data.items()
        if k.startswith("_task_") and isinstance(v, dict) and v.get("status") in ("done", "error", "cancelled")
    ]
    for key, task_data in completed:
        match task_data["status"]:
            case "done":
                turn_ctx.add_message(
                    role="system",
                    content=f"<task_result>{task_data['result']}</task_result>",
                )
            case "error":
                turn_ctx.add_message(
                    role="system",
                    content=f"<task_error>{task_data['error']}</task_error>",
                )
            case "cancelled":
                turn_ctx.add_message(
                    role="system",
                    content="<task_cancelled />",
                )
        del state.data[key]
```

### F2.5 — What Changes Where

| File | Change |
|------|--------|
| `models/config.py` | Add `ExecutionConfig`, `PreResponseConfig`, `OnCompleteConfig` |
| `models/config.py` → `AgentConfig` | Add `execution: ExecutionConfig` field |
| `operations/build.py` → `_bd_agent_class` | Override `on_user_turn_completed` for state-reactive injection |
| `operations/build.py` → `_bd_build_agent` | Wrap tools with `_bd_wrap_background_tool` when `execution.mode == "background"` |
| `models/state.py` → `SessionState` | No structural change — uses existing `data: dict[str, Any]` |

---

## F3. Task Queue with Priorities

### F3.1 — Problem Statement

When multiple background tasks are launched, we need:
- Priority ordering (urgent tasks first)
- Named tasks (user can reference them)
- Cancellable tasks
- Status tracking
- Callbacks when tasks complete

### F3.2 — YAML Schema — Session-Level Queue Config

```yaml
# config/sessions/web.yaml
name: web
# ...existing config...

task_queue:
  enabled: true
  max_concurrent: 3           # max parallel background tasks
  default_priority: 5         # 1=highest, 10=lowest
```

### F3.3 — TaskQueue Implementation

**Pure Python — `asyncio.PriorityQueue` + `asyncio.TaskGroup`:**

```python
@dataclasses.dataclass(order=True)
class QueuedTask:
    """Task entry in the priority queue."""
    priority: int
    task_id: str = dataclasses.field(compare=False)
    name: str = dataclasses.field(compare=False)
    coro: Coroutine = dataclasses.field(compare=False, repr=False)
    cancellable: bool = dataclasses.field(default=True, compare=False)
    _handle: asyncio.Task | None = dataclasses.field(default=None, compare=False, repr=False)


class TaskQueue:
    """Priority-based async task queue with cancellation support."""

    __slots__ = ("_queue", "_running", "_max_concurrent", "_results", "_semaphore")

    def __init__(self, max_concurrent: int = 3) -> None:
        self._queue: asyncio.PriorityQueue[QueuedTask] = asyncio.PriorityQueue()
        self._running: dict[str, QueuedTask] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def submit(
        self,
        task_id: str,
        name: str,
        coro: Coroutine,
        *,
        priority: int = 5,
        cancellable: bool = True,
    ) -> None:
        """Submit a task to the queue."""
        entry = QueuedTask(
            priority=priority, task_id=task_id, name=name,
            coro=coro, cancellable=cancellable,
        )
        self._results[task_id] = {"status": "queued", "name": name, "priority": priority}
        await self._queue.put(entry)
        asyncio.create_task(self._process())

    async def _process(self) -> None:
        """Process next task from queue."""
        await self._semaphore.acquire()
        try:
            entry = await self._queue.get()
            self._running[entry.task_id] = entry
            self._results[entry.task_id]["status"] = "running"
            entry._handle = asyncio.create_task(self._execute(entry))
        except Exception:
            self._semaphore.release()

    async def _execute(self, entry: QueuedTask) -> None:
        """Execute a single task and update results."""
        try:
            result = await entry.coro
            self._results[entry.task_id] = {
                "status": "done", "name": entry.name, "result": result,
            }
        except asyncio.CancelledError:
            self._results[entry.task_id] = {
                "status": "cancelled", "name": entry.name,
            }
        except Exception as exc:
            self._results[entry.task_id] = {
                "status": "error", "name": entry.name, "error": str(exc),
            }
        finally:
            self._running.pop(entry.task_id, None)
            self._semaphore.release()

    async def cancel(self, task_id: str) -> bool:
        """Cancel a running or queued task. Returns True if cancelled."""
        if entry := self._running.get(task_id):
            if entry.cancellable and entry._handle:
                entry._handle.cancel()
                return True
        return False

    async def cancel_by_name(self, name: str) -> int:
        """Cancel all tasks matching a name. Returns count cancelled."""
        cancelled = 0
        for tid, entry in list(self._running.items()):
            if entry.name == name and entry.cancellable and entry._handle:
                entry._handle.cancel()
                cancelled += 1
        return cancelled

    @property
    def pending(self) -> list[dict[str, Any]]:
        """Return status of all tasks."""
        return [v for v in self._results.values() if v["status"] in ("queued", "running")]

    @property
    def completed(self) -> list[dict[str, Any]]:
        """Return completed task results (pop on read)."""
        done = [
            (k, v) for k, v in self._results.items()
            if v["status"] in ("done", "error", "cancelled")
        ]
        return [self._results.pop(k) for k, _ in done]
```

**Where:** New file `operations/queue.py`.

### F3.4 — Integration with SessionState

```python
@dataclasses.dataclass(slots=True)
class SessionState:
    shared: State
    data: dict[str, Any] = dataclasses.field(default_factory=dict)
    task_queue: TaskQueue | None = dataclasses.field(default=None)
```

**Build-time in `_bd_build_session`:**

```python
if cfg.task_queue and cfg.task_queue.enabled:
    session_state.task_queue = TaskQueue(max_concurrent=cfg.task_queue.max_concurrent)
```

---

## F4. Interruption & Cancellation System

### F4.1 — Problem Statement

The user should be able to:
1. Cancel a specific background task by name ("stop searching for X")
2. Cancel all background tasks ("stop everything")
3. Ask about running tasks ("what are you working on?")

### F4.2 — YAML Schema — Agent-Level Cancellation Config

```yaml
# config/agents/assistant.yaml
name: assistant

execution:
  mode: background
  cancellation:
    enabled: true
    # The agent's instructions already cover intent detection.
    # These tools are auto-injected at build time:
    auto_tools:
      - cancel_task           # cancel by name
      - cancel_all_tasks      # cancel all
      - list_tasks            # show running tasks
```

### F4.3 — Config Model

```python
class CancellationConfig(BaseModelYAML):
    """Task cancellation configuration."""
    enabled: bool = False
    auto_tools: list[Literal["cancel_task", "cancel_all_tasks", "list_tasks"]] = Field(
        default_factory=lambda: ["cancel_task", "cancel_all_tasks", "list_tasks"],
    )
```

Add to `ExecutionConfig`:

```python
class ExecutionConfig(BaseModelYAML):
    mode: Literal["background", "blocking"] = "blocking"
    pre_response: PreResponseConfig = Field(default_factory=PreResponseConfig)
    on_complete: OnCompleteConfig = Field(default_factory=OnCompleteConfig)
    cancellation: CancellationConfig = Field(default_factory=CancellationConfig)
```

### F4.4 — Auto-Injected Cancellation Tools (built dynamically)

```python
def _bd_build_cancel_tools(self) -> list[FunctionTool]:
    """Build task management tools for the front agent."""
    tools: list[FunctionTool] = []

    @function_tool(name="cancel_task", description="Cancel a specific background task by name.")
    async def _cancel(context: RunContext[SessionState], task_name: str) -> str:
        """Cancel a running background task.
        Args:
            task_name: Name of the task to cancel.
        """
        queue = context.userdata.task_queue
        if queue is None:
            return "No task queue available."
        count = await queue.cancel_by_name(task_name)
        return f"Cancelled {count} task(s) matching '{task_name}'." if count else f"No running task named '{task_name}'."
    tools.append(_cancel)

    @function_tool(name="cancel_all_tasks", description="Cancel all running background tasks.")
    async def _cancel_all(context: RunContext[SessionState]) -> str:
        """Cancel all running background tasks."""
        queue = context.userdata.task_queue
        if queue is None:
            return "No task queue available."
        cancelled = 0
        for tid in list(queue._running):
            if await queue.cancel(tid):
                cancelled += 1
        return f"Cancelled {cancelled} task(s)."
    tools.append(_cancel_all)

    @function_tool(name="list_tasks", description="List all running and queued background tasks.")
    async def _list(context: RunContext[SessionState]) -> str:
        """List all active background tasks with their status."""
        queue = context.userdata.task_queue
        if queue is None:
            return "No task queue available."
        tasks = queue.pending
        if not tasks:
            return "No tasks currently running."
        return "\n".join(f"- {t['name']} (priority: {t['priority']}, status: {t['status']})" for t in tasks)
    tools.append(_list)

    return tools
```

**Build-time injection in `_bd_build_agent`:**

```python
if agent_cfg.execution.cancellation.enabled:
    auto_tool_names = set(agent_cfg.execution.cancellation.auto_tools)
    cancel_tools = self._bd_build_cancel_tools()
    tools.extend(t for t in cancel_tools if t.info.name in auto_tool_names)
```

### F4.5 — Native LiveKit Interruption (Tool-Level)

For tools that run in `blocking` mode but are long-running, LiveKit provides
native interruption detection:

```yaml
# config/agents/researcher.yaml
name: researcher
tools:
  - web_search:
      interruptible: true     # use speech_handle.wait_if_not_interrupted
  - analyze_data:
      interruptible: false    # use context.disallow_interruptions()
```

**Build-time tool wrapper:**

```python
def _bd_wrap_interruptible_tool(self, tool: FunctionTool, interruptible: bool) -> FunctionTool:
    """Wrap tool with LiveKit-native interruption handling."""
    @function_tool(name=tool.info.name, description=tool.info.description)
    async def _wrapper(context: RunContext[SessionState], **kwargs) -> str | None:
        if not interruptible:
            context.disallow_interruptions()
            return await tool.execute(context, **kwargs)

        future = asyncio.ensure_future(tool.execute(context, **kwargs))
        await context.speech_handle.wait_if_not_interrupted([future])

        if context.speech_handle.interrupted:
            future.cancel()
            return None
        return future.result()

    return _wrapper
```

---

## F5. State-Reactive Agent Pattern

### F5.1 — Problem Statement

The front agent needs to monitor `SessionState` for changes made by background tasks
and react accordingly — injecting results into the conversation when they arrive.

### F5.2 — Dual Delivery Architecture (Recommended)

Two complementary mechanisms work together. This is the same architecture described
in F2.4 — here we show the full dynamic Agent class that implements both.

| Mechanism | Role | Pipeline-safe | Proactive | When |
|-----------|------|---------------|-----------|------|
| Event-driven callback | **Recommended** — proactive delivery | Conditional (idle-only) | Yes | Task completion |
| `on_user_turn_completed` | **Fallback** — guaranteed safe delivery | Yes | No | Every user turn |

**The event-driven approach is recommended** because it produces the most natural,
human-like behavior: when a task completes, the agent proactively shares results —
just like a human colleague would say "by the way, I found that thing you asked about."

The key concern — pipeline safety — is addressed by guarding on `agent_state`.
The callback only fires `generate_reply` when the agent is `"idle"` or `"listening"`,
meaning the pipeline is not mid-cycle. If the agent is currently speaking, the
callback waits — the result stays in state and either:

- The event-driven callback fires once the agent returns to idle, or
- `on_user_turn_completed` picks it up on the next user turn (fallback).

**Why not just event-driven?** `update_chat_ctx()` + `generate_reply()` from a
background `asyncio.Task` is **unsafe** if the pipeline is mid-cycle (e.g. the LLM
is generating, TTS is synthesizing, or the user is speaking). Mutating `chat_ctx`
concurrently can corrupt state or cause interleaving. The idle guard prevents this,
but if timing is unlucky, the fallback catches it.

**Why not just turn-based?** If the user is silent, results accumulate without being
delivered. The user might wait 30 seconds for a result that's been ready for 25.

**Both together:** event-driven handles the common case proactively, turn-based acts
as a safety net for edge cases where the event-driven guard was too conservative.

### F5.3 — Dynamic Agent Class with Background Awareness

```python
@staticmethod
def _bd_agent_class(name: str, cfg: AgentConfig) -> type[Agent]:
    """Build dynamic Agent subclass with all configured lifecycle hooks."""
    greeting = cfg.greeting
    exec_cfg = cfg.execution
    has_background = exec_cfg.mode == "background"

    class _ConfiguredAgent(Agent):

        async def on_enter(self) -> None:
            if greeting:
                await self.session.generate_reply(instructions=greeting)

        async def on_user_turn_completed(self, turn_ctx, new_message):
            # PRIMARY: inject completed background task results (pipeline-safe)
            if has_background:
                queue: TaskQueue | None = self.session.userdata.task_queue
                if queue:
                    for result in queue.completed:
                        match result["status"]:
                            case "done":
                                turn_ctx.add_message(
                                    role="system",
                                    content=f"<task_result name='{result['name']}'>"
                                            f"{result['result']}</task_result>",
                                )
                            case "error":
                                turn_ctx.add_message(
                                    role="system",
                                    content=f"<task_error name='{result['name']}'>"
                                            f"{result['error']}</task_error>",
                                )
                            case "cancelled":
                                turn_ctx.add_message(
                                    role="system",
                                    content=f"<task_cancelled name='{result['name']}' />",
                                )

            # Block empty turns
            if not new_message.text_content:
                raise StopResponse()

    _ConfiguredAgent.__name__ = _ConfiguredAgent.__qualname__ = f"Agent_{name}"
    return _ConfiguredAgent
```

### F5.4 — Event-Driven Proactive Notification (Secondary)

The background task callback in `_bd_wrap_background_tool` (F2.4) calls
`_try_proactive_notify`, which guards against concurrent pipeline mutation:

```python
def _try_proactive_notify(session, task_id, name, result, on_complete):
    """Proactively notify ONLY if pipeline is idle — otherwise let turn-based handle it."""
    if not hasattr(session, "agent_state") or session.agent_state not in ("idle", "listening"):
        return  # on_user_turn_completed picks it up safely on the next turn

    agent = session.current_agent
    chat_ctx = agent.chat_ctx.copy()
    chat_ctx.add_message(
        role="system",
        content=f"<task_complete name='{name}'>{result}</task_complete>",
    )
    asyncio.create_task(agent.update_chat_ctx(chat_ctx))
    session.generate_reply(instructions=on_complete.instructions)
```

### F5.5 — Flow Diagram

```
Background task completes
│
├─ Is agent idle/listening?
│  ├─ YES → SECONDARY: update_chat_ctx + generate_reply (proactive)
│  │        Result delivered immediately. Agent speaks unprompted.
│  │
│  └─ NO  → Result stays in state.data / TaskQueue
│           ↓
│           User speaks → on_user_turn_completed fires
│           ↓
│           PRIMARY: inject result into turn_ctx
│           ↓
│           LLM generates response that includes the result
```

This dual-delivery pattern gives the most natural experience: the agent shares
results proactively when the user is waiting, and weaves them into conversation
naturally when the user is active.

---

## F6. Pre-Response System

### F6.1 — Three Pre-Response Modes

| Mode | Source | Use case |
|------|--------|----------|
| Fixed text | `pre_response.message` | Simple acknowledgment |
| Fast LLM | `pre_response.model` + `prompt` | Context-aware filler |
| Silence | `pre_response.enabled: false` | No acknowledgment |

### F6.2 — Build-Time: Fixed Text Pre-Response

```python
if pre_cfg.enabled and pre_cfg.message:
    context.session.say(pre_cfg.message, add_to_chat_ctx=False)
```

### F6.3 — Build-Time: Fast LLM Pre-Response

Uses the same pattern as the `fast-preresponse` example:

```python
if pre_cfg.enabled and pre_cfg.model:
    fast_llm = inference.LLM(pre_cfg.model)
    fast_ctx = context.session.current_agent.chat_ctx.copy(
        exclude_instructions=True,
        exclude_function_call=True,
    ).truncate(max_items=3)
    fast_ctx.items.insert(0, ChatMessage(role="system", content=[pre_cfg.prompt]))

    context.session.say(
        fast_llm.chat(chat_ctx=fast_ctx).to_str_iterable(),
        add_to_chat_ctx=False,
    )
```

---

## F7. Per-Tool Execution Config

### F7.1 — Problem Statement

Not all tools should run in background. Some are quick lookups (blocking), others
are heavy searches (background). This should be configurable per-tool.

### F7.2 — YAML Schema

```yaml
# config/agents/assistant.yaml
name: assistant

tools:
  - web_search                   # simple: uses agent-level execution.mode
  - name: deep_research          # detailed: per-tool override
    execution:
      mode: background
      priority: 2
      cancellable: true
      pre_response:
        enabled: true
        message: "Searching in depth, this may take a moment..."
  - name: quick_lookup
    execution:
      mode: blocking
      interruptible: false
```

### F7.3 — Config Model

```python
class ToolRef(BaseModelYAML):
    """Tool reference with optional per-tool execution config."""
    name: str
    execution: ExecutionConfig | None = None
    priority: int = 5
    cancellable: bool = True
    interruptible: bool = True

# In AgentConfig:
tools: list[str | ToolRef] = Field(default_factory=list)

@model_validator(mode="after")
def _normalize_tools(self) -> AgentConfig:
    """Normalize tools to always be ToolRef."""
    self.tools = [
        ToolRef(name=t) if isinstance(t, str) else t
        for t in self.tools
    ]
    return self
```

### F7.4 — Build-Time Resolution

```python
def _bd_build_agent(self, name, session_cfg, *, chat_ctx=NOT_GIVEN):
    agent_cfg = self.config.agents[name]
    tools = []

    for tool_ref in agent_cfg.tools:
        raw_tool = self.tools.get(tool_ref.name)
        if raw_tool is None:
            continue

        exec_cfg = tool_ref.execution or agent_cfg.execution

        match exec_cfg.mode:
            case "background":
                wrapped = self._bd_wrap_background_tool(raw_tool, exec_cfg, tool_ref)
                tools.append(wrapped)
            case "blocking" if not tool_ref.interruptible:
                wrapped = self._bd_wrap_interruptible_tool(raw_tool, interruptible=False)
                tools.append(wrapped)
            case _:
                tools.append(raw_tool)
    # ...
```

---

## F8. Complete YAML Examples

### F8.1 — Session with Task Queue

```yaml
# config/sessions/research.yaml
name: research
stt: whisperlive
tts: kokoro
vad: silero
llm:
  provider: google
  model: gemini-2.0-flash

max_tool_steps: 10
allow_interruptions: true
preemptive_generation: true

task_queue:
  enabled: true
  max_concurrent: 3
  default_priority: 5

dispatcher: assistant
agents:
  - assistant
  - researcher
  - analyst

state:
  - user_name
  - conversation_topic
  - research_results
```

### F8.2 — Front Agent with Background Execution

```yaml
# config/agents/assistant.yaml
name: assistant
instructions: |
  You are a research assistant. You can search the web directly for
  quick queries, or hand off complex research to specialists.
  When you launch background tasks, continue chatting naturally.
  If a task completes while talking, share the results.
  The user can ask you to cancel tasks or check their status.
greeting: |
  Hello! I'm your research assistant. I can search, analyze, and
  research topics — even multiple things at once. What interests you?

tools:
  - name: web_search
    execution:
      mode: background
      priority: 3
      cancellable: true
      pre_response:
        enabled: true
        message: "Let me search that for you. Meanwhile, anything else?"

execution:
  mode: background
  pre_response:
    enabled: true
    message: "Working on it! What else would you like to know?"
  on_complete:
    notify: true
    instructions: "A background search just completed. Naturally share the results."
  cancellation:
    enabled: true
    auto_tools:
      - cancel_task
      - cancel_all_tasks
      - list_tasks

handoffs:
  - target: researcher
    context: carry
  - target: analyst
    context: truncated
    truncate_items: 10
```

### F8.3 — Specialist Agent (Blocking, No Background)

```yaml
# config/agents/researcher.yaml
name: researcher
instructions: |
  You are a deep research analyst. Perform thorough multi-source
  research. When done, transfer back to the assistant.
tools:
  - web_search
  - name: deep_analysis
    execution:
      mode: blocking
      interruptible: true

handoffs:
  - assistant
```

---

## F9. Implementation Roadmap

### Phase 1 — Handoff Validation (minimal effort)

| Task | File | Effort |
|------|------|--------|
| Add cross-reference validation | `operations/load.py` | Small |
| Add `HandoffConfig` model | `models/config.py` | Small |
| Update `_bd_build_handoff` for context modes | `operations/build.py` | Small |

**LiveKit tools:** None new — uses existing `function_tool`, `Agent`, `chat_ctx`.

### Phase 2 — Background Execution + Pre-Response

| Task | File | Effort |
|------|------|--------|
| Add `ExecutionConfig` + sub-models | `models/config.py` | Small |
| Add `_bd_wrap_background_tool` | `operations/build.py` | Medium |
| Enhance `_bd_agent_class` with `on_user_turn_completed` | `operations/build.py` | Medium |
| Pre-response in tool wrapper | `operations/build.py` | Small |

**LiveKit tools:** `session.say(add_to_chat_ctx=False)`, `session.generate_reply(instructions=...)`, `agent.update_chat_ctx()`, `StopResponse`.
**Python tools:** `asyncio.create_task`, `asyncio.Future`.

### Phase 3 — Task Queue

| Task | File | Effort |
|------|------|--------|
| Implement `TaskQueue` | `operations/queue.py` (new) | Medium |
| Add `TaskQueueConfig` to `SessionConfig` | `models/config.py` | Small |
| Wire queue into `SessionState` | `models/state.py` | Small |
| Initialize queue in `_bd_build_session` | `operations/build.py` | Small |

**LiveKit tools:** None — pure Python.
**Python tools:** `asyncio.PriorityQueue`, `asyncio.Semaphore`, `asyncio.Task`.

### Phase 4 — Cancellation & Task Management

| Task | File | Effort |
|------|------|--------|
| Add `CancellationConfig` | `models/config.py` | Small |
| Build `_bd_build_cancel_tools` | `operations/build.py` | Medium |
| Inject cancel tools in `_bd_build_agent` | `operations/build.py` | Small |

**LiveKit tools:** `function_tool`, `RunContext`.
**Python tools:** `asyncio.Task.cancel()`.

### Phase 5 — Per-Tool Execution Config

| Task | File | Effort |
|------|------|--------|
| Add `ToolRef` model | `models/config.py` | Small |
| Normalize tools in `AgentConfig` validator | `models/config.py` | Small |
| Per-tool wrapping in `_bd_build_agent` | `operations/build.py` | Medium |
| `_bd_wrap_interruptible_tool` | `operations/build.py` | Small |

**LiveKit tools:** `context.disallow_interruptions()`, `speech_handle.wait_if_not_interrupted()`.

---

## F10. LiveKit Native Tools Used Per Feature

| Feature | LiveKit API | Python stdlib |
|---------|-------------|---------------|
| **Greeting** | `session.generate_reply(instructions=...)` | — |
| **Handoffs** | `function_tool` returning `Agent` | — |
| **Context carry** | `Agent(chat_ctx=self.chat_ctx)` | — |
| **Context truncate** | `chat_ctx.copy(...).truncate(max_items=N)` | — |
| **Pre-response (fixed)** | `session.say(text, add_to_chat_ctx=False)` | — |
| **Pre-response (LLM)** | `session.say(llm.chat().to_str_iterable(), add_to_chat_ctx=False)` | — |
| **Background exec** | `session.generate_reply()` (callback) | `asyncio.create_task` |
| **State injection** | `agent.update_chat_ctx()` | — |
| **Interruption detect** | `speech_handle.wait_if_not_interrupted()` | `asyncio.ensure_future` |
| **Disallow interrupt** | `context.disallow_interruptions()` | — |
| **Turn guardrail** | `on_user_turn_completed` + `StopResponse` | — |
| **Task queue** | — | `asyncio.PriorityQueue`, `Semaphore` |
| **Task cancel** | — | `asyncio.Task.cancel()` |
| **Cancel tools** | `function_tool` (auto-injected) | — |
| **List tasks** | `function_tool` (auto-injected) | — |
| **Error handling** | `session.on("error")`, `ToolError` | — |
| **Shutdown** | `session.shutdown()`, `EndCallTool` | — |

---

## F11. Architecture — Dynamic Build Flow

```
YAML Config Load (Loader)
│
├── agents/*.yaml ──→ AgentConfig (with HandoffConfig, ExecutionConfig, ToolRef)
├── sessions/*.yaml ─→ SessionConfig (with TaskQueueConfig)
├── mcps/*.yaml ────→ McpTransport
└── tools/ (scan) ──→ dict[str, FunctionTool]
│
▼ Validation
├── Agent exists in session.agents?
├── Handoff targets exist?
├── Tools exist in scanned registry?
└── MCP configs exist?
│
▼ Build (Builder)
│
├── Build SessionState
│   └── TaskQueue (if enabled)
│
├── Build AgentSession
│   ├── Session-level tools
│   ├── Session-level MCP servers
│   └── Session-level interruption/turn config
│
└── Build Agent (per agent_cfg)
    │
    ├── Resolve tools
    │   ├── Simple tool → use as-is
    │   ├── Background tool → wrap with _bd_wrap_background_tool
    │   └── Non-interruptible → wrap with _bd_wrap_interruptible_tool
    │
    ├── Build handoff tools
    │   └── Per HandoffConfig → function_tool with context mode
    │
    ├── Build cancel tools (if cancellation.enabled)
    │   └── cancel_task, cancel_all_tasks, list_tasks
    │
    ├── Resolve MCP servers
    │
    └── Build dynamic Agent subclass
        ├── on_enter → greeting
        ├── on_user_turn_completed → background result injection + guardrails
        └── tools = [resolved + handoff + cancel]
```
