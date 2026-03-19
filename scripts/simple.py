"""Agente simple — un asistente conversacional básico.

    make script simple
"""

from __future__ import annotations

import logging
import sys

logging.getLogger("google_genai.models").setLevel(logging.WARNING)

from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, cli
from livekit.plugins import google


##### AGENT #####


class Assistant(Agent):

    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "Eres Ana, una asistente amable y directa. Hablas SIEMPRE en español.\n"
                "Conversa con naturalidad. Respuestas cortas y claras."
            ),
        )


##### SERVER #####

server = AgentServer()


@server.rtc_session(agent_name="simple")
async def entrypoint(ctx: agents.JobContext) -> None:
    session = AgentSession(llm=google.LLM(model="gemini-2.0-flash"))
    await session.start(agent=Assistant(), room=ctx.room)


if __name__ == "__main__":
    sys.argv = [sys.argv[0], "console", "--text"]
    cli.run_app(server)
