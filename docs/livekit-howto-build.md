# LiveKit Agents — How to Build

> Comprehensive reference for building voice AI agents with the **Python SDK**.
> Based on `livekit-agents ~= 1.4` — docs rendered 2026-03-10.

---

## Table of Contents

1. [Agent Server & Entrypoint](#1-agent-server--entrypoint)
2. [AgentSession — Full Configuration](#2-agentsession--full-configuration)
3. [Agent — Full Configuration](#3-agent--full-configuration)
4. [Tools (Function Tools)](#4-tools-function-tools)
5. [MCP Servers](#5-mcp-servers)
6. [Handoffs (Multi-Agent)](#6-handoffs-multi-agent)
7. [Guardrails (Pipeline Nodes)](#7-guardrails-pipeline-nodes)
8. [Tasks & Task Groups](#8-tasks--task-groups)
9. [Session Events & State](#9-session-events--state)
10. [Speech & Audio Control](#10-speech--audio-control)
11. [External Data & RAG](#11-external-data--rag)
12. [Workflows — Putting It All Together](#12-workflows--putting-it-all-together)

---

## 1. Agent Server & Entrypoint

Every LiveKit agent app starts with an `AgentServer` and a decorated entrypoint.

```python
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentServer, AgentSession, Agent, cli

load_dotenv(".env.local")

server = AgentServer()

def prewarm(proc: agents.JobProcess):
    """Load expensive resources once per process (e.g. VAD model)."""
    from livekit.plugins import silero
    proc.userdata["vad"] = silero.VAD.load()

server.setup_fnc = prewarm

@server.rtc_session(agent_name="my-agent")
async def entrypoint(ctx: agents.JobContext):
    session = AgentSession(...)
    await session.start(agent=..., room=ctx.room)
    await ctx.connect()

if __name__ == "__main__":
    cli.run_app(server)
```

### `rtc_session` Options

| Parameter | Description |
|---|---|
| `agent_name` | Name for agent dispatch (must be explicitly dispatched if set) |
| `type` | Server type: per-room or per-publisher |
| `on_request` | Callback when a new request is received |
| `on_session_end` | Callback when session ends (session reports) |

---

## 2. AgentSession — Full Configuration

The `AgentSession` is the main orchestrator. It manages VAD → STT → LLM → TTS pipeline,
user input, tool execution, and events.

### Constructor — All Parameters

```python
from livekit.agents import AgentSession, inference, room_io
from livekit.plugins import silero, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

session = AgentSession(
    # ── AI Models ──
    stt="deepgram/nova-3:en",                           # str shorthand or STT instance
    llm="openai/gpt-4.1-mini",                          # str shorthand or LLM instance
    tts="cartesia/sonic-3:9626c31c-...",                 # str shorthand or TTS instance
    vad=silero.VAD.load(),                               # Voice Activity Detection

    # ── Turn Detection & Interruptions ──
    turn_detection=MultilingualModel(),                  # or "vad", "stt", "manual", or None
    min_endpointing_delay=0.5,                           # seconds to wait before considering turn complete
    max_endpointing_delay=3.0,                           # max wait when turn detector says user may continue
    allow_interruptions=True,                            # allow user to interrupt agent speech
    min_interruption_words=0,                            # min transcribed words to trigger interruption
    min_interruption_duration=0.5,                       # min speech duration before interruption
    discard_audio_if_uninterruptible=True,               # drop buffered audio when agent can't be interrupted
    false_interruption_timeout=2.0,                      # seconds before signaling false interruption
    resume_false_interruption=True,                      # resume speech after false interruption

    # ── Tools & MCP ──
    tools=[],                                            # session-level tools shared by all agents
    mcp_servers=[],                                      # MCP servers shared by all agents
    max_tool_steps=3,                                    # max consecutive tool calls per LLM turn
    ivr_detection=False,                                 # detect IVR systems (telephony)

    # ── User Interaction ──
    min_consecutive_speech_delay=0.0,                    # min delay between agent utterances (seconds)
    user_away_timeout=15.0,                              # silence before user state → "away" (None to disable)

    # ── Text Processing ──
    tts_text_transforms=["filter_markdown", "filter_emoji"],  # or None to disable
    use_tts_aligned_transcript=False,                    # use TTS-aligned transcript for transcription node

    # ── Performance ──
    preemptive_generation=False,                         # start LLM+TTS before end-of-turn confirmed

    # ── Video ──
    video_sampler=None,                                  # custom video sampler or VoiceActivityVideoSampler

    # ── State ──
    userdata=None,                                       # arbitrary per-session data (dataclass recommended)
)
```

### Starting the Session

```python
await session.start(
    agent=MyAgent(),
    room=ctx.room,
    room_options=room_io.RoomOptions(
        # ── Input ──
        audio_input=room_io.AudioInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
        text_input=True,                                 # enable text input (default True)
        video_input=False,                               # enable video input (default False)

        # ── Output ──
        audio_output=True,                               # enable audio output (default True)
        text_output=room_io.TextOutputOptions(
            sync_transcription=True,                     # sync transcript with audio
        ),

        # ── Participants ──
        participant_identity=None,                       # link to specific participant (default: first joiner)
        participant_kinds=[                              # accepted participant types
            # rtc.ParticipantKind.PARTICIPANT_KIND_SIP,
            # rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD,
        ],

        # ── Cleanup ──
        close_on_disconnect=True,                        # close session when participant leaves
        delete_room_on_close=False,                      # delete room when session ends
    ),
)
await ctx.connect()
```

---

## 3. Agent — Full Configuration

An `Agent` defines instructions, tools, overrides, and pipeline nodes.

### Constructor — All Parameters

```python
from livekit.agents import Agent

agent = Agent(
    instructions="You are a helpful voice AI assistant.",
    id=None,                                             # auto-generated from class name (snake_case)

    # ── Conversation ──
    chat_ctx=None,                                       # initial ChatContext (or NOT_GIVEN for empty)

    # ── Tools & MCP ──
    tools=[],                                            # list of FunctionTool / RawFunctionTool / Toolset
    mcp_servers=[],                                      # MCP servers for this agent

    # ── Plugin Overrides (override session defaults) ──
    stt=None,                                            # STT instance, model string, or None
    llm=None,                                            # LLM instance, model string, or None
    tts=None,                                            # TTS instance, model string, or None
    vad=None,                                            # VAD instance or None

    # ── Turn Detection Override ──
    turn_detection=None,                                 # override session turn detection

    # ── Interruption Override ──
    allow_interruptions=None,                            # override session interruption setting
    min_consecutive_speech_delay=None,                   # override session speech delay
    use_tts_aligned_transcript=None,                     # override session TTS alignment
    min_endpointing_delay=None,                          # override session endpointing
    max_endpointing_delay=None,                          # override session endpointing
)
```

### Subclass Pattern (Recommended)

```python
from livekit.agents import Agent, function_tool, RunContext, inference

class CustomerServiceAgent(Agent):
    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="You are a customer service agent for Acme Corp.",
            chat_ctx=chat_ctx,
            tools=[shared_lookup_tool],                  # external tools
            mcp_servers=[
                mcp.MCPServerHTTP("https://api.example.com/mcp"),
            ],
            tts=inference.TTS(                           # custom voice for this agent
                model="cartesia/sonic-3",
                voice="6f84f4b8-58a2-430c-8c79-688dad597532",
            ),
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="Greet the user warmly."
        )

    async def on_exit(self) -> None:
        await self.session.generate_reply(
            instructions="Say goodbye before transferring."
        )

    @function_tool()
    async def search_orders(self, context: RunContext, order_id: str) -> dict:
        """Search for an order by ID."""
        return await fetch_order(order_id)

    @function_tool()
    async def transfer_to_billing(self, context: RunContext):
        """Transfer to billing specialist."""
        return BillingAgent(chat_ctx=self.chat_ctx), "Transferring to billing"
```

### Runtime Updates

```python
await agent.update_instructions("New instructions here.")
await agent.update_tools(agent.tools + [new_tool])
await agent.update_tools(agent.tools - [old_tool])
await agent.update_tools([tool_a, tool_b])             # replace all
await agent.update_chat_ctx(new_chat_ctx)
```

---

## 4. Tools (Function Tools)

### 4.1 — Decorator on Agent Class

```python
from livekit.agents import Agent, function_tool, RunContext

class MyAgent(Agent):
    @function_tool()
    async def lookup_weather(
        self,
        context: RunContext,
        location: str,
    ) -> dict:
        """Look up weather information for a given location."""
        return {"weather": "sunny", "temperature_f": 70}
```

### 4.2 — Standalone (Shared Across Agents)

```python
@function_tool()
async def lookup_user(context: RunContext, user_id: str) -> dict:
    """Look up a user's information by ID."""
    return {"name": "John Doe", "email": "john@example.com"}

class AgentA(Agent):
    def __init__(self):
        super().__init__(instructions="...", tools=[lookup_user])

class AgentB(Agent):
    def __init__(self):
        super().__init__(instructions="...", tools=[lookup_user])
```

### 4.3 — Programmatic (Dynamic) Creation

```python
class Assistant(Agent):
    def _setter_for(self, field: str):
        async def set_value(context: RunContext, value: str):
            return f"{field} set to {value}"
        return set_value

    def __init__(self):
        super().__init__(
            instructions="...",
            tools=[
                function_tool(
                    self._setter_for("phone"),
                    name="set_phone",
                    description="Record the user's phone number.",
                ),
                function_tool(
                    self._setter_for("email"),
                    name="set_email",
                    description="Record the user's email.",
                ),
            ],
        )
```

### 4.4 — From Raw JSON Schema

```python
raw_schema = {
    "type": "function",
    "name": "get_weather",
    "description": "Get weather for a location.",
    "parameters": {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City e.g. New York"}
        },
        "required": ["location"],
        "additionalProperties": False,
    },
}

@function_tool(raw_schema=raw_schema)
async def get_weather(raw_arguments: dict[str, object], context: RunContext):
    return f"The weather in {raw_arguments['location']} is sunny"
```

### 4.5 — From Database / External Source

```python
def create_db_tool(table: str, operation: str):
    schema = {
        "type": "function",
        "name": f"{operation}_{table}",
        "description": f"Perform {operation} on {table} table",
        "parameters": {
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": f"Record ID to {operation}"}
            },
            "required": ["record_id"],
        },
    }

    async def handler(raw_arguments: dict[str, object], context: RunContext):
        return f"Performed {operation} on {table} for {raw_arguments['record_id']}"

    return function_tool(handler, raw_schema=schema)

tools = [
    create_db_tool("users", "read"),
    create_db_tool("users", "update"),
    create_db_tool("users", "delete"),
]
```

### 4.6 — Error Handling

```python
from livekit.agents import ToolError

@function_tool()
async def my_tool(self, context: RunContext, location: str):
    """Look up location data."""
    if location == "mars":
        raise ToolError("This location is not yet supported.")
    return {"status": "ok"}
```

### 4.7 — Speech Inside Tools

```python
@function_tool()
async def process_order(self, context: RunContext, order_id: str):
    """Process an order and notify the user."""
    self.session.generate_reply(
        instructions=f"Processing order {order_id}. This may take a moment."
    )
    await context.wait_for_playout()    # MUST use this inside tools
    result = await do_processing(order_id)
    return result
```

### 4.8 — Interruption Control

```python
@function_tool()
async def critical_payment(self, context: RunContext, amount: float):
    """Process a payment (cannot be interrupted)."""
    context.disallow_interruptions()
    await charge_card(amount)
    return "Payment processed"
```

### 4.9 — Long-Running Tool with Interruption Check

```python
@function_tool()
async def long_search(self, context: RunContext, query: str):
    """Search that respects interruptions."""
    import asyncio
    wait_for_result = asyncio.ensure_future(heavy_search(query))
    await context.speech_handle.wait_if_not_interrupted([wait_for_result])

    if context.speech_handle.interrupted:
        wait_for_result.cancel()
        return None                                      # discarded when interrupted

    return await wait_for_result
```

### 4.10 — Cached TTS Hold Message in Tool

```python
from livekit import rtc

HOLD_FRAMES: list[rtc.AudioFrame] = []

async def preload_hold_message(tts) -> None:
    global HOLD_FRAMES
    async for event in tts.synthesize("Let me check that for you."):
        HOLD_FRAMES.append(event.frame)

class MyAgent(Agent):
    @function_tool()
    async def check_status(self, context: RunContext, order_id: str) -> str:
        """Check order status with hold message."""
        async def cached_audio():
            for frame in HOLD_FRAMES:
                yield frame

        hold_handle = context.session.say(
            "Let me check that for you.",
            audio=cached_audio(),
            add_to_chat_ctx=False,
        )
        result = await fetch_order_status(order_id)

        if not hold_handle.interrupted and not hold_handle.done():
            hold_handle.interrupt()

        return result
```

### 4.11 — Frontend RPC Tool

```python
from livekit.agents import function_tool, get_job_context, RunContext, ToolError
import json

@function_tool()
async def get_user_location(context: RunContext, high_accuracy: bool):
    """Retrieve the user's geolocation from the frontend via RPC."""
    try:
        room = get_job_context().room
        participant_identity = next(iter(room.remote_participants))
        response = await room.local_participant.perform_rpc(
            destination_identity=participant_identity,
            method="getUserLocation",
            payload=json.dumps({"highAccuracy": high_accuracy}),
            response_timeout=10.0 if high_accuracy else 5.0,
        )
        return response
    except Exception:
        raise ToolError("Unable to retrieve user location")
```

---

## 5. MCP Servers

LiveKit natively supports [Model Context Protocol](https://modelcontextprotocol.io/) servers.

```bash
uv add "livekit-agents[mcp]~=1.4"
```

### 5.1 — MCPServerHTTP (Remote)

```python
from livekit.agents import mcp

mcp.MCPServerHTTP(
    url="https://your-server.com/sse",                   # auto-detect: /sse → SSE, /mcp → streamable HTTP
    transport_type=None,                                  # explicit: "sse" | "streamable_http" | None
    allowed_tools=["search", "create"],                   # None = all tools
    headers={"Authorization": "Bearer token"},
    timeout=5,                                            # connection timeout (seconds)
    sse_read_timeout=300,                                 # SSE read timeout (seconds)
    client_session_timeout_seconds=5,
)
```

### 5.2 — MCPServerStdio (Local Process)

```python
mcp.MCPServerStdio(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    env={"NODE_ENV": "production"},
    cwd="/path/to/project",
    client_session_timeout_seconds=5,
)
```

### 5.3 — Attach to Session (All Agents Share)

```python
session = AgentSession(
    mcp_servers=[
        mcp.MCPServerHTTP("https://api.example.com/mcp"),
        mcp.MCPServerStdio(command="uvx", args=["mcp-server-sqlite", "db.sqlite"]),
    ],
    # ... stt, llm, tts, etc.
)
```

### 5.4 — Attach to Specific Agent

```python
class SpecializedAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions="...",
            mcp_servers=[
                mcp.MCPServerHTTP(
                    "https://billing-api.example.com/mcp",
                    allowed_tools=["get_invoice", "create_refund"],
                ),
            ],
        )
```

### 5.5 — MCP Lifecycle

```python
server = mcp.MCPServerHTTP("https://api.example.com/mcp")
await server.initialize()                                # establish connection
tools = await server.list_tools()                        # discover tools (cached)
server.invalidate_cache()                                # force re-fetch next list_tools()
await server.aclose()                                    # cleanup
```

---

## 6. Handoffs (Multi-Agent)

### 6.1 — Basic Handoff via Tool Return

```python
from livekit.agents import Agent, function_tool, RunContext

class TriageAgent(Agent):
    def __init__(self):
        super().__init__(instructions="Route the user to the right specialist.")

    async def on_enter(self) -> None:
        await self.session.generate_reply(instructions="Ask the user what they need help with.")

    @function_tool()
    async def route_to_billing(self, context: RunContext):
        """Transfer to billing when user has payment/invoice questions."""
        return BillingAgent(chat_ctx=self.chat_ctx), "Transferring to billing"

    @function_tool()
    async def route_to_support(self, context: RunContext):
        """Transfer to technical support for product issues."""
        return SupportAgent(chat_ctx=self.chat_ctx), "Transferring to support"

class BillingAgent(Agent):
    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="You are a billing specialist.",
            chat_ctx=chat_ctx,
            tts=inference.TTS(model="cartesia/sonic-3", voice="billing-voice-id"),
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="Introduce yourself as a billing specialist."
        )

class SupportAgent(Agent):
    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="You are a technical support specialist.",
            chat_ctx=chat_ctx,
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="Introduce yourself as tech support."
        )
```

### 6.2 — Return Value Variants

```python
# Handoff only (no tool result to LLM)
return SomeAgent()

# Handoff + message (LLM sees the message, then handoff)
return SomeAgent(), "Transferring to specialist"

# Regular tool return (no handoff)
return {"status": "ok"}

# Conditional handoff
return NextAgent() if condition else None
```

### 6.3 — Programmatic Agent Swap (No Tool)

```python
session.update_agent(NewAgent())
```

### 6.4 — Context Preservation

```python
# Fresh context (default) — new agent starts clean
return NewAgent()

# Carry full conversation history
return NewAgent(chat_ctx=self.chat_ctx)

# Full session history is always at:
session.history
```

### 6.5 — Conditional Handoff with Userdata

```python
from dataclasses import dataclass

@dataclass
class SessionInfo:
    user_name: str | None = None
    age: int | None = None

class IntakeAgent(Agent):
    def __init__(self):
        super().__init__(instructions="Collect the user's name and age.")

    @function_tool()
    async def record_name(self, context: RunContext[SessionInfo], name: str):
        """Record the user's name."""
        context.userdata.user_name = name
        return self._handoff_if_done()

    @function_tool()
    async def record_age(self, context: RunContext[SessionInfo], age: int):
        """Record the user's age."""
        context.userdata.age = age
        return self._handoff_if_done()

    def _handoff_if_done(self):
        ud = self.session.userdata
        if ud.user_name and ud.age:
            return ServiceAgent()
        return None

class ServiceAgent(Agent):
    def __init__(self):
        super().__init__(instructions="You are a customer service agent.")

    async def on_enter(self) -> None:
        ud: SessionInfo = self.session.userdata
        await self.session.generate_reply(
            instructions=f"Greet {ud.user_name} by name."
        )
```

### 6.6 — Per-Agent Plugin Overrides

```python
class ManagerAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions="You are a manager handling escalations.",
            llm="openai/gpt-4.1",                       # more capable model
            tts=inference.TTS(
                model="cartesia/sonic-3",
                voice="manager-voice-id",
            ),
        )
```

### 6.7 — Lifecycle Hooks

```python
class MyAgent(Agent):
    async def on_enter(self) -> None:
        """Called when this agent becomes active."""
        await self.session.generate_reply(instructions="Greet the user.")

    async def on_exit(self) -> None:
        """Called before giving control to another agent."""
        await self.session.generate_reply(instructions="Say goodbye.")
```

---

## 7. Guardrails (Pipeline Nodes)

LiveKit has no built-in `Guardrail` class. Instead, implement guardrails through
**pipeline nodes** and **lifecycle hooks**.

### 7.1 — Input Guardrail via `on_user_turn_completed`

```python
from livekit.agents import Agent, ChatContext, ChatMessage, StopResponse

class GuardedAgent(Agent):
    def __init__(self):
        super().__init__(instructions="You are a helpful assistant.")

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage,
    ) -> None:
        user_text = new_message.text_content() or ""

        # Block prompt injection
        if any(p in user_text.lower() for p in ["ignore previous", "system prompt"]):
            new_message.content = ["I'm sorry, I can't process that request."]
            return

        # Redact PII
        import re
        new_message.content = [
            re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED-SSN]", user_text)
        ]
```

### 7.2 — Abort Reply Entirely

```python
async def on_user_turn_completed(
    self, turn_ctx: ChatContext, new_message: ChatMessage,
) -> None:
    if not new_message.text_content:
        raise StopResponse()                             # no response generated
```

### 7.3 — Output Guardrail via `llm_node` (Dual-LLM Moderation)

```python
from livekit.agents import Agent, inference
from livekit.agents.llm import ChatContext, ChatMessage

class ContentFilterAgent(Agent):
    def __init__(self):
        super().__init__(instructions="You are a helpful agent.")
        self.moderator_llm = inference.LLM(model="openai/gpt-4.1-mini")

    async def evaluate_content(self, text: str) -> bool:
        ctx = ChatContext([
            ChatMessage(
                type="message", role="system",
                content=["Respond ONLY with 'SAFE' or 'UNSAFE'."],
            ),
            ChatMessage(
                type="message", role="user",
                content=[f"Evaluate: {text}"],
            ),
        ])
        response = ""
        async with self.moderator_llm.chat(chat_ctx=ctx) as stream:
            async for chunk in stream:
                c = getattr(chunk.delta, "content", None) if hasattr(chunk, "delta") else str(chunk)
                if c:
                    response += c
        return "UNSAFE" not in response.strip().upper()

    async def llm_node(self, chat_ctx, tools, model_settings=None):
        async def process_stream():
            buffer = ""
            chunk_buffer = []
            sentence_ends = {".", "!", "?"}

            async with self.session.llm.chat(
                chat_ctx=chat_ctx, tools=tools, tool_choice=None
            ) as stream:
                async for chunk in stream:
                    content = (
                        getattr(chunk.delta, "content", None)
                        if hasattr(chunk, "delta") else
                        chunk if isinstance(chunk, str) else None
                    )
                    chunk_buffer.append(chunk)

                    if content:
                        buffer += content
                        if any(c in buffer for c in sentence_ends):
                            last_end = max(
                                buffer.rfind(c) for c in sentence_ends if c in buffer
                            )
                            sentence = buffer[: last_end + 1]
                            buffer = buffer[last_end + 1 :]

                            if not await self.evaluate_content(sentence):
                                yield "I can't respond to that."
                                return

                            for buffered_chunk in chunk_buffer:
                                yield buffered_chunk
                            chunk_buffer = []

        return process_stream()
```

### 7.4 — STT Guardrail via `stt_node`

```python
async def stt_node(self, audio, model_settings):
    """Post-process transcription (e.g. profanity filter)."""
    async for event in Agent.default.stt_node(self, audio, model_settings):
        # Modify transcribed text before it reaches LLM
        yield event
```

### 7.5 — TTS Guardrail via `tts_node`

```python
async def tts_node(self, text, model_settings):
    """Modify text before speech synthesis."""
    async def filtered():
        async for chunk in text:
            yield chunk.replace("competitor_name", "another provider")

    async for frame in Agent.default.tts_node(self, filtered(), model_settings):
        yield frame
```

### 7.6 — Transcription Cleanup via `transcription_node`

```python
async def transcription_node(self, text, model_settings):
    """Clean up text before sending transcript to user."""
    async for delta in text:
        yield delta.replace("😘", "")
```

### 7.7 — Prompt-Based Guardrails

```python
Agent(
    instructions="""You are a customer service assistant for Acme Corp.

    ## Guardrails
    - NEVER discuss competitor products.
    - NEVER share internal pricing formulas.
    - If asked about topics outside your scope, politely redirect.
    - If the user is abusive, end the conversation professionally.
    - ALWAYS verify user identity before sharing account details.
    """
)
```

### Guardrails Summary

| Type | Where | How |
|---|---|---|
| Input validation | `on_user_turn_completed` | Modify / block `new_message` |
| Abort reply | `on_user_turn_completed` | `raise StopResponse()` |
| Output filtering | `llm_node` override | Buffer + moderate before forwarding |
| Audio preprocessing | `stt_node` override | Filter audio or transcript |
| TTS postprocessing | `tts_node` override | Modify text before synthesis |
| Transcript cleanup | `transcription_node` override | Clean text before user sees it |
| Behavioral | Agent `instructions` | Prompt engineering |

---

## 8. Tasks & Task Groups

Tasks are focused units that run to completion and return a typed result.

### 8.1 — Defining a Task

```python
from livekit.agents import AgentTask, function_tool

class CollectConsent(AgentTask[bool]):
    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="Ask for recording consent. Get a clear yes or no.",
            chat_ctx=chat_ctx,
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="Ask permission to record the call."
        )

    @function_tool
    async def consent_given(self) -> None:
        """User gives consent."""
        self.complete(True)

    @function_tool
    async def consent_denied(self) -> None:
        """User denies consent."""
        self.complete(False)
```

### 8.2 — Running a Task from an Agent

```python
class CustomerServiceAgent(Agent):
    async def on_enter(self) -> None:
        consent = await CollectConsent(chat_ctx=self.chat_ctx)
        if consent:
            await self.session.generate_reply(instructions="Offer your assistance.")
        else:
            await self.session.generate_reply(instructions="Can't proceed without consent.")
```

### 8.3 — Typed Results

```python
from dataclasses import dataclass

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
        """Record the user's name."""
        self._data["name"] = name
        self._check()

    @function_tool()
    async def record_email(self, email: str):
        """Record the user's email."""
        self._data["email"] = email
        self._check()

    @function_tool()
    async def record_phone(self, phone: str):
        """Record the user's phone."""
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

### 8.4 — Task Groups (Ordered Multi-Step Flows)

```python
from livekit.agents.beta.workflows import TaskGroup

task_group = TaskGroup(
    chat_ctx=self.chat_ctx,                              # shared context
    summarize_chat_ctx=True,                             # summarize when done (default True)
    return_exceptions=False,                             # propagate exceptions (default False)
)

task_group.add(
    lambda: CollectConsent(),
    id="consent",
    description="Collect recording consent",
)
task_group.add(
    lambda: GetContactTask(),
    id="contact",
    description="Collect contact information",
)

results = await task_group
print(results.task_results)
# {"consent": True, "contact": ContactInfo(name="...", email="...", phone="...")}
```

Task groups support **regression** — users can go back to correct earlier steps.

---

## 9. Session Events & State

### 9.1 — Events

```python
from livekit.agents import UserStateChangedEvent, AgentStateChangedEvent

@session.on("agent_state_changed")
def on_agent_state(ev: AgentStateChangedEvent):
    # ev.new_state: "initializing" | "idle" | "listening" | "thinking" | "speaking"
    print(f"Agent → {ev.new_state}")

@session.on("user_state_changed")
def on_user_state(ev: UserStateChangedEvent):
    # ev.new_state: "speaking" | "listening" | "away"
    print(f"User → {ev.new_state}")

@session.on("user_input_transcribed")
def on_transcript(ev):
    print(f"User said: {ev.transcript}")

@session.on("conversation_item_added")
def on_item(ev):
    print(f"New conversation item: {ev.item}")

@session.on("close")
def on_close(ev):
    print("Session closed")
```

### 9.2 — Userdata (Shared State)

```python
from dataclasses import dataclass

@dataclass
class SessionInfo:
    user_name: str | None = None
    order_id: str | None = None

session = AgentSession[SessionInfo](
    userdata=SessionInfo(),
    # ...
)

# Access from any agent
self.session.userdata.user_name

# Access from any tool via RunContext
context.userdata.user_name
```

### 9.3 — Turn Detection Modes

```python
# Turn detector model (recommended)
session = AgentSession(
    turn_detection=MultilingualModel(),                  # or EnglishModel()
    vad=silero.VAD.load(),
)

# VAD only
session = AgentSession(turn_detection="vad", vad=silero.VAD.load())

# STT endpointing (e.g. AssemblyAI, Deepgram Flux)
session = AgentSession(turn_detection="stt", stt=assemblyai.STT(), vad=silero.VAD.load())

# Manual (push-to-talk)
session = AgentSession(turn_detection="manual")
session.input.set_audio_enabled(False)                   # start muted
# ... session.interrupt(), session.clear_user_turn(), session.commit_user_turn()
```

---

## 10. Speech & Audio Control

### 10.1 — `session.say()` (Predefined Message)

```python
await session.say(
    "Hello, how can I help you?",
    allow_interruptions=False,
    add_to_chat_ctx=True,                                # add to conversation history
)
```

### 10.2 — `session.generate_reply()` (LLM-Driven)

```python
# From instructions (not added to chat history)
session.generate_reply(instructions="Greet the user warmly.")

# From user input (added to chat history)
session.generate_reply(user_input="How is the weather today?")
```

### 10.3 — SpeechHandle

```python
handle = session.say("Processing your request...")

# Wait for completion
await handle.wait_for_playout()

# Check state
handle.interrupted                                       # was it interrupted?
handle.done()                                            # is it finished?

# Add callback
handle.add_done_callback(lambda _: print("done"))

# Interrupt programmatically
handle.interrupt()
session.interrupt()                                      # or from session
```

### 10.4 — Background Audio ("Thinking" Sounds)

```python
from livekit.agents import BackgroundAudioPlayer, AudioConfig, BuiltinAudioClip

background_audio = BackgroundAudioPlayer(
    thinking_sound=[
        AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.8),
        AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.7),
    ],
)
await background_audio.start(room=ctx.room, agent_session=session)
```

### 10.5 — Pre-Synthesized / Cached Audio

```python
from livekit.agents.utils.audio import audio_frames_from_file

await session.say(
    "Your phrase",
    audio=audio_frames_from_file(path, sample_rate=24000, num_channels=1),
)
```

---

## 11. External Data & RAG

### 11.1 — Initial Context (Before Session Starts)

```python
from livekit.agents.llm import ChatContext
import json

@server.rtc_session(agent_name="my-agent")
async def entrypoint(ctx: agents.JobContext):
    metadata = json.loads(ctx.job.metadata)

    initial_ctx = ChatContext()
    initial_ctx.add_message(
        role="assistant",
        content=f"The user's name is {metadata['user_name']}.",
    )

    session = AgentSession(...)
    await session.start(
        agent=MyAgent(chat_ctx=initial_ctx),
        room=ctx.room,
    )
```

### 11.2 — RAG via `on_user_turn_completed`

```python
async def on_user_turn_completed(
    self, turn_ctx: ChatContext, new_message: ChatMessage,
) -> None:
    rag_content = await vector_search(new_message.text_content())
    turn_ctx.add_message(
        role="assistant",
        content=f"Relevant context: {rag_content}",
    )
```

### 11.3 — RAG via Tool Call

```python
@function_tool()
async def search_knowledge_base(self, context: RunContext, query: str) -> str:
    """Search the knowledge base for relevant information."""
    import asyncio

    async def _status_update(delay: float = 0.5):
        await asyncio.sleep(delay)
        context.session.generate_reply(
            instructions=f'Searching for "{query}", please wait...'
        )

    status_task = asyncio.create_task(_status_update(0.5))
    result = await perform_search(query)
    status_task.cancel()
    return result
```

---

## 12. Workflows — Putting It All Together

### Architecture

```
AgentServer
└── rtc_session (entrypoint)
    └── AgentSession
        ├── Agent (active)
        │   ├── Tools (@function_tool, standalone, dynamic, raw_schema)
        │   ├── MCP Servers (HTTP, Stdio)
        │   ├── Tasks (AgentTask[T])
        │   ├── Pipeline Nodes (stt_node, llm_node, tts_node, transcription_node)
        │   └── Lifecycle Hooks (on_enter, on_exit, on_user_turn_completed)
        ├── Agent (handoff target) → same capabilities
        ├── TaskGroup (ordered multi-step)
        ├── Events (agent_state, user_state, transcript, close)
        ├── Speech (say, generate_reply, SpeechHandle)
        ├── Background Audio
        └── Userdata (shared state across agents)
```

### Complete Example — Multi-Agent with Everything

```python
from dataclasses import dataclass
from livekit import agents
from livekit.agents import (
    Agent, AgentSession, AgentTask, BackgroundAudioPlayer, AudioConfig,
    BuiltinAudioClip, ChatContext, ChatMessage, RunContext, StopResponse,
    function_tool, inference, mcp, room_io, cli, AgentServer,
)
from livekit.plugins import silero, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel


##### SESSION STATE #####

@dataclass
class UserInfo:
    name: str | None = None
    verified: bool = False


##### TASKS #####

class VerifyIdentity(AgentTask[bool]):
    def __init__(self):
        super().__init__(instructions="Verify the user's identity by asking for their account PIN.")

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="Ask the user for their 4-digit account PIN."
        )

    @function_tool
    async def verify_pin(self, context: RunContext[UserInfo], pin: str) -> None:
        """Verify the provided PIN."""
        if pin == "1234":
            context.userdata.verified = True
            self.complete(True)
        else:
            self.session.generate_reply(instructions="That PIN is incorrect. Try again.")


##### AGENTS #####

class GreeterAgent(Agent):
    """Entry point — greets and routes."""

    def __init__(self):
        super().__init__(
            instructions="You are the front desk. Greet users and route them.",
            tools=[],
        )

    async def on_enter(self) -> None:
        verified = await VerifyIdentity()
        if not verified:
            await self.session.say("Sorry, I couldn't verify your identity.", allow_interruptions=False)
            return

        await self.session.generate_reply(
            instructions="The user is verified. Ask how you can help."
        )

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage,
    ) -> None:
        user_text = new_message.text_content() or ""
        if any(w in user_text.lower() for w in ["ignore instructions", "system prompt"]):
            new_message.content = ["I can't process that request."]

    @function_tool()
    async def route_to_billing(self, context: RunContext):
        """Transfer to billing specialist."""
        return BillingAgent(chat_ctx=self.chat_ctx), "Transferring to billing"

    @function_tool()
    async def route_to_support(self, context: RunContext):
        """Transfer to technical support."""
        return SupportAgent(chat_ctx=self.chat_ctx), "Transferring to support"


class BillingAgent(Agent):
    """Billing specialist with MCP tools."""

    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="You are a billing specialist. Help with invoices and payments.",
            chat_ctx=chat_ctx,
            mcp_servers=[
                mcp.MCPServerHTTP(
                    "https://billing-api.example.com/mcp",
                    allowed_tools=["get_invoice", "create_refund"],
                ),
            ],
            tts=inference.TTS(model="cartesia/sonic-3", voice="billing-voice-id"),
        )

    async def on_enter(self) -> None:
        ud: UserInfo = self.session.userdata
        await self.session.generate_reply(
            instructions=f"Introduce yourself as billing specialist. Address {ud.name} by name."
        )

    @function_tool()
    async def return_to_main(self, context: RunContext):
        """Return to the main menu."""
        return GreeterAgent(), "Returning to main menu"


class SupportAgent(Agent):
    """Tech support with guardrailed output."""

    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="You are tech support. Help troubleshoot product issues.",
            chat_ctx=chat_ctx,
            llm="openai/gpt-4.1",                       # more capable model for support
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="Introduce yourself as tech support."
        )

    async def tts_node(self, text, model_settings):
        """Replace competitor mentions before speech synthesis."""
        async def filtered():
            async for chunk in text:
                yield chunk.replace("CompetitorX", "another provider")
        async for frame in Agent.default.tts_node(self, filtered(), model_settings):
            yield frame

    @function_tool()
    async def search_docs(self, context: RunContext, query: str) -> str:
        """Search product documentation."""
        context.disallow_interruptions()
        return await search_knowledge_base(query)

    @function_tool()
    async def return_to_main(self, context: RunContext):
        """Return to the main menu."""
        return GreeterAgent(), "Returning to main menu"


##### SERVER #####

server = AgentServer()

def prewarm(proc: agents.JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

server.setup_fnc = prewarm

@server.rtc_session(agent_name="voice-assistant")
async def entrypoint(ctx: agents.JobContext):
    session = AgentSession[UserInfo](
        userdata=UserInfo(),
        stt="deepgram/nova-3:en",
        llm="openai/gpt-4.1-mini",
        tts="cartesia/sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
        vad=ctx.proc.userdata["vad"],
        turn_detection=MultilingualModel(),
        max_tool_steps=5,
        preemptive_generation=True,
    )

    await session.start(
        agent=GreeterAgent(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
        ),
    )

    background_audio = BackgroundAudioPlayer(
        thinking_sound=[AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.7)],
    )
    await background_audio.start(room=ctx.room, agent_session=session)
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
```

### Decision Matrix

| Need | Use |
|---|---|
| Distinct persona / instructions | Separate `Agent` subclass |
| Different tool access / permissions | Separate `Agent` with own `tools` / `mcp_servers` |
| Different voice / model | Agent-level `tts` / `llm` / `stt` overrides |
| Collect structured info | `AgentTask[T]` |
| Ordered multi-step flow | `TaskGroup` |
| External API call | `@function_tool` |
| External tool server | `MCPServerHTTP` / `MCPServerStdio` |
| Block bad input | `on_user_turn_completed` + `StopResponse` |
| Filter LLM output | `llm_node` override |
| Modify speech output | `tts_node` override |
| Transfer conversation | Tool returning `Agent` instance |
| Shared session state | `session.userdata` (dataclass) |
| User feedback during tools | `session.say()` / `session.generate_reply()` |
| Thinking sounds | `BackgroundAudioPlayer` |

### Reference Links

| Topic | URL |
|---|---|
| Tools | https://docs.livekit.io/agents/build/tools |
| Agents & Handoffs | https://docs.livekit.io/agents/logic/agents-handoffs |
| Workflows | https://docs.livekit.io/agents/logic/workflows |
| Tasks & Task Groups | https://docs.livekit.io/agents/build/tasks |
| Pipeline Nodes | https://docs.livekit.io/agents/build/nodes |
| Sessions | https://docs.livekit.io/agents/logic/sessions |
| Turn Detection | https://docs.livekit.io/agents/logic/turns |
| Speech & Audio | https://docs.livekit.io/agents/multimodality/audio |
| External Data & RAG | https://docs.livekit.io/agents/build/external-data |
| MCP API Reference | https://docs.livekit.io/reference/python/livekit/agents/llm/mcp.html |
| Content Filter Recipe | https://docs.livekit.io/recipes/llm_powered_content_filter/ |
| Prompting Guide | https://docs.livekit.io/agents/start/prompting/ |
| Python API Reference | https://docs.livekit.io/reference/python/livekit/agents/index.html |
