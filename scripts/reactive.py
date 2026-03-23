"""ReactiveSession prototype — LiveKit voice/text chat with policy-driven orchestration.

Three modes:
  uv run python scripts/reactive.py              # LiveKit text chat (safe default)
  uv run python scripts/reactive.py --voice      # LiveKit voice chat (evoice STT/TTS)
  uv run python scripts/reactive.py --sim        # Event simulator (no LLM)
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass, field

from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, RunContext, cli, function_tool
from livekit.agents.llm import ChatContext, ChatMessage
from livekit.plugins import google, silero

from e_agents.arch.models import Event, EventKind, ReactiveState
from e_agents.arch.policies import AwayPolicy, TaskCompletedPolicy, TurnEscalationPolicy
from e_agents.arch.protocols import Policy
from e_agents.arch.session import ReactiveSession
from e_agents.rtc.adapters.stt.evoice import EVoiceSTT
from e_agents.rtc.adapters.tts.evoice import EVoiceTTS

logging.getLogger("google_genai.models").setLevel(logging.WARNING)

_VOICE_MODE = False


##### LOGGING #####


_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_MAGENTA = "\033[35m"
_GREEN = "\033[32m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

_TAG_COLORS: dict[str, str] = {
    "react": _YELLOW,
    "policy": _MAGENTA,
    "action": f"{_BOLD}{_GREEN}",
    "state": _DIM,
    "agent": _CYAN,
    "system": _BOLD,
    "tick": f"{_DIM}{_YELLOW}",
}


def _log(tag: str, msg: str) -> None:
    color = _TAG_COLORS.get(tag, "")
    print(f"  {color}[{tag.upper():<8}]{_RESET} {msg}")


##### SESSION CONTEXT #####


@dataclass
class SessionContext:
    """Stored in session.userdata — bridges agent tools to reactive system."""

    state: ReactiveState
    reactor: ReactiveSession | None = None
    pending_results: list[str] = field(default_factory=list)


##### LIVEKIT SESSION HANDLE #####


class LiveKitSession:
    """SessionHandle wrapping a real LiveKit AgentSession.

    Voice mode: interrupt/say/generate_reply work natively via audio.
    Text mode: generate_reply output is lost (CLI loop limitation), so we queue
    instructions in pending_results for turn-boundary injection.
    """

    __slots__ = ("_session", "_text_mode")

    def __init__(self, session: AgentSession[SessionContext], *, text_mode: bool = False) -> None:
        self._session = session
        self._text_mode = text_mode

    async def interrupt(self) -> None:
        if self._text_mode:
            _log("action", "interrupt() → skipped (text mode)")
            return
        _log("action", "interrupt()")
        self._session.interrupt()

    async def say(self, *, text: str) -> None:
        _log("action", f"say({text!r})")
        if self._text_mode:
            instructions = f"Di exactamente esto al usuario: {text}"
            self._session.generate_reply(instructions=instructions)
            self._session.userdata.pending_results.append(instructions)
            _log("action", "⚡ queued for next turn (text mode)")
        else:
            self._session.say(text, add_to_chat_ctx=True)

    async def generate_reply(self, *, instructions: str) -> None:
        preview = instructions[:80] + ("..." if len(instructions) > 80 else "")
        _log("action", f"generate_reply({preview!r})")
        self._session.generate_reply(instructions=instructions)
        if self._text_mode:
            self._session.userdata.pending_results.append(instructions)
            _log("action", "⚡ queued for next turn (text mode)")

    async def update_instructions(self, *, instructions: str) -> None:
        _log("action", f"update_instructions({instructions[:50]!r}) (stub)")

    async def swap_agent(self, *, agent_id: str) -> None:
        _log("action", f"swap_agent({agent_id!r}) (stub)")


##### BACKGROUND TASKS #####


async def _bg_weather(ctx: SessionContext, city: str) -> None:
    """Simulate weather API — emits TASK_COMPLETED after delay."""
    _log("agent", f"⏳ bg_weather({city!r}) started — 5s")
    await asyncio.sleep(5.0)
    result = f"Clima en {city}: Soleado, 22°C, humedad 45%, viento suave del norte"
    _log("agent", f"✅ bg_weather({city!r}) done → TASK_COMPLETED")
    ctx.reactor.emit(Event(
        kind=EventKind.TASK_COMPLETED,
        payload={"message": result},
    ))


async def _bg_news(ctx: SessionContext, topic: str) -> None:
    """Simulate news API — emits TASK_COMPLETED after delay."""
    _log("agent", f"⏳ bg_news({topic!r}) started — 8s")
    await asyncio.sleep(8.0)
    result = (
        f"Noticias sobre {topic}: "
        "(1) Gran avance en investigación con IA generativa. "
        "(2) Nuevo acuerdo comercial entre UE y Mercosur. "
        "(3) Descubrimiento de exoplaneta habitable a 40 años luz."
    )
    _log("agent", f"✅ bg_news({topic!r}) done → TASK_COMPLETED")
    ctx.reactor.emit(Event(
        kind=EventKind.TASK_COMPLETED,
        payload={"message": result},
    ))


##### AGENT #####


_ANA_INSTRUCTIONS = """\
Eres Ana, una asistente amable y directa. Hablas SIEMPRE en español.
Conversa con naturalidad. Respuestas cortas y claras.

Cuando lances una búsqueda, sigue conversando con el usuario mientras llegan \
los resultados. No menciones herramientas, sistemas internos ni arquitectura. \
Habla como una persona normal.
Cuando recibas resultados (llegarán como instrucciones del sistema), compártelos \
de forma natural.\
"""


class Ana(Agent):
    """Simple agent — knows nothing about ReactiveSession."""

    def __init__(self) -> None:
        super().__init__(instructions=_ANA_INSTRUCTIONS)

    @function_tool()
    async def check_weather(
        self, context: RunContext[SessionContext], city: str,
    ) -> str:
        """Consulta el clima actual de una ciudad.

        Args:
            city: Ciudad para consultar el clima.
        """
        _log("agent", f"🔧 check_weather({city!r}) → bg task launched")
        asyncio.create_task(_bg_weather(context.userdata, city))
        return f"Buscando el clima en {city}. Resultados en unos segundos."

    @function_tool()
    async def lookup_news(
        self, context: RunContext[SessionContext], topic: str,
    ) -> str:
        """Busca noticias recientes sobre un tema.

        Args:
            topic: Tema a buscar.
        """
        _log("agent", f"🔧 lookup_news({topic!r}) → bg task launched")
        asyncio.create_task(_bg_news(context.userdata, topic))
        return f"Buscando noticias sobre {topic}. Resultados en unos segundos."

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage,
    ) -> None:
        """Inject pending reactive results into the next LLM turn."""
        ctx: SessionContext = self.session.userdata
        if not ctx.pending_results:
            return
        for instructions in ctx.pending_results:
            turn_ctx.add_message(
                role="system",
                content=f"[Resultado de tarea en segundo plano] {instructions}",
            )
            _log("agent", "📨 pending result injected into turn context")
        ctx.pending_results.clear()


##### SERVER #####


server = AgentServer()


@server.rtc_session(agent_name="reactive")
async def entrypoint(ctx: agents.JobContext) -> None:
    """Wire ReactiveSession + LiveKit agent together."""
    text_mode = not _VOICE_MODE
    state = ReactiveState()
    policies: tuple[Policy, ...] = (
        TaskCompletedPolicy(),
        AwayPolicy(timeout=30.0),
    )

    session_ctx = SessionContext(state=state)

    if text_mode:
        session = AgentSession[SessionContext](
            userdata=session_ctx,
            llm=google.LLM(model="gemini-2.0-flash"),
            max_tool_steps=5,
        )
    else:
        session = AgentSession[SessionContext](
            userdata=session_ctx,
            llm=google.LLM(model="gemini-2.0-flash"),
            stt=EVoiceSTT(language="es"),
            tts=EVoiceTTS(),
            vad=silero.VAD.load(),
            max_tool_steps=5,
            allow_interruptions=True,
            min_endpointing_delay=0.5,
            max_endpointing_delay=3.0,
        )

    lk_handle = LiveKitSession(session, text_mode=text_mode)
    reactor = ReactiveSession(lk_handle, state, policies, tick_interval=2.0, log=_log)
    session_ctx.reactor = reactor

    asyncio.create_task(reactor.run())
    await session.start(agent=Ana(), room=ctx.room)


##### CONSOLE SIMULATOR #####


class ConsoleSession:
    """SessionHandle for the event simulator — prints actions."""

    async def interrupt(self) -> None:
        _log("action", "interrupt()")

    async def say(self, *, text: str) -> None:
        _log("action", f"say({text!r})")

    async def generate_reply(self, *, instructions: str) -> None:
        _log("action", f"generate_reply(instructions={instructions!r})")

    async def update_instructions(self, *, instructions: str) -> None:
        _log("action", f"update_instructions({instructions!r})")

    async def swap_agent(self, *, agent_id: str) -> None:
        _log("action", f"swap_agent({agent_id!r})")


_HELP: dict[str, str] = {
    "speak": "User starts speaking",
    "silent": "User stops speaking (increments turn)",
    "away": "User goes away",
    "done <msg>": "Background task completed",
    "fail <msg>": "Background task failed",
    "set <k> <v>": "Set state.data[key] = value",
    "state": "Print current state",
    "help": "Show commands",
    "quit": "Exit",
}


def _parse_input(line: str) -> Event | str | None:
    parts = line.strip().split(maxsplit=1)
    if not parts:
        return None
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    match cmd:
        case "speak":
            return Event(kind=EventKind.USER_SPEAKING)
        case "silent":
            return Event(kind=EventKind.USER_SILENT)
        case "away":
            return Event(kind=EventKind.USER_AWAY)
        case "done":
            return Event(kind=EventKind.TASK_COMPLETED, payload={"message": arg or "done"})
        case "fail":
            return Event(kind=EventKind.TASK_FAILED, payload={"error": arg or "unknown"})
        case "state" | "help" | "quit":
            return cmd
        case "set":
            return f"set:{arg}"
        case _:
            return None


async def run_console(*, tick_interval: float = 2.0, away_timeout: float = 10.0) -> None:
    """Interactive event simulator (no LLM — manual event injection)."""
    state = ReactiveState()
    session = ConsoleSession()
    policies: tuple[Policy, ...] = (
        AwayPolicy(timeout=away_timeout),
        TaskCompletedPolicy(),
        TurnEscalationPolicy(threshold=5),
    )

    reactive = ReactiveSession(
        session=session,
        state=state,
        policies=policies,
        tick_interval=tick_interval,
        log=_log,
    )

    task = asyncio.create_task(reactive.run())
    print("\n  ReactiveSession Simulator — type 'help' for commands\n")

    try:
        while True:
            line = await asyncio.to_thread(input, "> ")
            result = _parse_input(line)

            match result:
                case Event() as event:
                    reactive.emit(event)
                    await asyncio.sleep(0.05)
                case "state":
                    s = reactive.state
                    print(f"  user={s.user_state} agent={s.agent_state} turns={s.turn_count}")
                    print(f"  last_activity={s.last_user_activity:.1f}")
                    print(f"  data={s.data}")
                case "help":
                    for cmd, desc in _HELP.items():
                        print(f"  {cmd:<16} {desc}")
                case "quit":
                    break
                case str(s) if s.startswith("set:"):
                    kv = s[4:].split(maxsplit=1)
                    if len(kv) == 2:
                        reactive.state.data[kv[0]] = kv[1]
                        print(f"  state.data[{kv[0]!r}] = {kv[1]!r}")
                    else:
                        print("  Usage: set <key> <value>")
                case _:
                    print("  Unknown command. Type 'help'.")

    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        reactive.stop()
        await task


##### MAIN #####


if __name__ == "__main__":
    if "--sim" in sys.argv:
        asyncio.run(run_console())
    elif "--voice" in sys.argv:
        _VOICE_MODE = True
        sys.argv = [sys.argv[0], "console"]
        cli.run_app(server)
    else:
        sys.argv = [sys.argv[0], "console", "--text"]
        cli.run_app(server)
