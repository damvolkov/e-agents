"""e-agents — instantiates shared State, builds all module apps, and runs the stack."""

from __future__ import annotations

from e_agents.api.app import create_app as create_api_app
from e_agents.cli.app import create_app as create_cli_app
from e_agents.rtc.app import create_app as create_rtc_app
from e_agents.shared.adapters.searxng import SearXNGAdapter
from e_agents.shared.core.logger import log_banner
from e_agents.shared.core.settings import settings as st
from e_agents.shared.state import State


def main() -> None:
    log_banner(st.API_NAME, st.API_VERSION)

    ##### STATE #####
    state = State()
    state.register_adapter(SearXNGAdapter())

    ##### MODULE APPS #####
    api = create_api_app(state)
    rtc = create_rtc_app(state)
    cli = create_cli_app(state, api=api, rtc=rtc)

    ##### RUN #####
    cli()


if __name__ == "__main__":
    main()
