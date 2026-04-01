# =============================================================================
# e-agents Makefile
# =============================================================================
PROJECT ?= e-agents
VERSION ?= latest
DEBUG ?= true
ENVIRONMENT ?= DEV
PACKAGE ?= src/e_agents
SESSION ?= web
LANGUAGE ?= es

# OS Detection
OS := $(shell uname -s)

# ANSI Escape codes
BOLD   := \033[1m
RESET  := \033[0m
GREEN  := \033[1;32m
YELLOW := \033[0;33m
BLUE   := \033[0;34m
CYAN   := \033[0;36m
RED    := \033[0;31m

# Environment
-include .env
ifneq (,$(wildcard .env))
    $(eval export $(shell sed -ne 's/ *#.*$$//; /./ s/=.*$$// p' .env))
endif
export PYTHONPATH := $(CURDIR)/src

COMPOSE_FILE := compose.yml

.PHONY: help install sync lock lint format type test test-integration \
        infra infra-down build logs \
        run console join token stt script download clean

# -----------------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------------
help:
	@echo "$(BOLD)$(BLUE)e-agents$(RESET) - Multi-agent Voice AI Template"
	@echo ""
	@echo "$(BOLD)Setup:$(RESET)"
	@echo "  $(GREEN)make install$(RESET)      Install uv, dependencies, and pre-commit hooks"
	@echo "  $(GREEN)make sync$(RESET)         Sync dependencies from lockfile"
	@echo "  $(GREEN)make lock$(RESET)         Update lockfile with current dependencies"
	@echo ""
	@echo "$(BOLD)Infrastructure:$(RESET)"
	@echo "  $(GREEN)make infra$(RESET)        Start compose services (Redis + LiveKit + API)"
	@echo "  $(GREEN)make infra-down$(RESET)   Stop all infrastructure services"
	@echo "  $(GREEN)make logs$(RESET)         Follow API container logs"
	@echo "  $(GREEN)make build$(RESET)        Build Docker image"
	@echo ""
	@echo "$(BOLD)Local Development:$(RESET)"
	@echo "  $(GREEN)make run$(RESET)          Start agent server (API runs in background)"
	@echo "  $(GREEN)make console$(RESET)      Start agent in console mode (local testing)"
	@echo "  $(GREEN)make join$(RESET)         Join a room as participant"
	@echo "  $(GREEN)make token$(RESET)        Generate LiveKit access token"
	@echo "  $(GREEN)make stt$(RESET)          Live mic → e-voice STT WS (requires ffmpeg + websocat)"
	@echo "  $(GREEN)make script$(RESET)       Run a script with infra (SCRIPT=path/to/script.py)"
	@echo ""
	@echo "$(BOLD)Variables:$(RESET)"
	@echo "  $(CYAN)SESSION$(RESET)=$(SESSION)    Session name"
	@echo "  $(CYAN)ROOM$(RESET)=test-room      Room name for join/token"
	@echo "  $(CYAN)IDENTITY$(RESET)=user       Participant identity"
	@echo "  $(CYAN)TTL$(RESET)=60              Token TTL in minutes"
	@echo ""
	@echo "$(BOLD)Quality:$(RESET)"
	@echo "  $(GREEN)make lint$(RESET)         Run ruff linter with auto-fix"
	@echo "  $(GREEN)make format$(RESET)       Format code with ruff"
	@echo "  $(GREEN)make type$(RESET)         Run type checker"
	@echo "  $(GREEN)make test$(RESET)         Run unit tests"
	@echo "  $(GREEN)make test-integration$(RESET) Run integration tests (requires services)"
	@echo ""
	@echo "$(BOLD)Cleanup:$(RESET)"
	@echo "  $(GREEN)make clean$(RESET)        Remove cache and build artifacts"

# -----------------------------------------------------------------------------
# Setup & Dependencies
# -----------------------------------------------------------------------------
install:
	@echo "$(GREEN)=== Installing system dependencies ===$(RESET)"
ifeq ($(OS),Linux)
	@echo "$(GREEN)=== Installing uv ===$(RESET)"
	@curl -LsSf https://astral.sh/uv/install.sh | sh
else ifeq ($(OS),Darwin)
	@command -v brew >/dev/null 2>&1 || { echo "$(RED)Error: Homebrew required$(RESET)"; exit 1; }
	@echo "$(GREEN)=== Installing uv ===$(RESET)"
	@brew install uv
else
	@echo "$(RED)Error: Unsupported OS: $(OS)$(RESET)"
	@exit 1
endif
	@echo "$(GREEN)=== Syncing Python dependencies ===$(RESET)"
	@uv sync --frozen
	@echo "$(GREEN)=== Installing pre-commit hooks ===$(RESET)"
	@uv run pre-commit install
	@echo "$(GREEN)=== Setup complete ===$(RESET)"

sync:
	@echo "$(GREEN)=== Syncing dependencies ===$(RESET)"
	@uv sync --dev
	@echo "$(GREEN)=== Sync complete ===$(RESET)"

download:
	@echo "$(GREEN)=== Downloading models to data/models/ ===$(RESET)"
	@uv run python scripts/download_models.py
	@echo "$(GREEN)=== Download complete ===$(RESET)"

lock:
	@echo "$(GREEN)=== Updating lockfile ===$(RESET)"
	@uv lock
	@echo "$(GREEN)=== Lockfile updated ===$(RESET)"

# -----------------------------------------------------------------------------
# Quality & Testing
# -----------------------------------------------------------------------------
lint:
	@echo "$(GREEN)=== Running linter ===$(RESET)"
	@uv run ruff check --fix $(PACKAGE)
	@echo "$(GREEN)=== Lint complete ===$(RESET)"

format:
	@echo "$(GREEN)=== Formatting code ===$(RESET)"
	@uv run ruff format $(PACKAGE)
	@echo "$(GREEN)=== Format complete ===$(RESET)"

type:
	@echo "$(GREEN)=== Running type checker ===$(RESET)"
	@uv run ty check
	@echo "$(GREEN)=== Type check complete ===$(RESET)"

test:
	@echo "$(GREEN)=== Running unit tests ===$(RESET)"
	@uv run python -m pytest tests/unit -v -m 'not slow'
	@echo "$(GREEN)=== Tests complete ===$(RESET)"

test-integration: _ensure-deps
	@echo "$(GREEN)=== Running integration tests ===$(RESET)"
	@uv run python -m pytest tests/integration -v -m slow
	@echo "$(GREEN)=== Integration tests complete ===$(RESET)"

# -----------------------------------------------------------------------------
# Infrastructure (Docker)
# -----------------------------------------------------------------------------
build:
	@echo "$(GREEN)=== Building Docker image ===$(RESET)"
	@docker compose -f $(COMPOSE_FILE) build api
	@echo "$(GREEN)=== Build complete ===$(RESET)"

infra:
	@echo "$(GREEN)=== Starting compose services ===$(RESET)"
	@docker compose -f $(COMPOSE_FILE) up -d redis livekit api
	@echo "$(GREEN)=== Services ready ===$(RESET)"
	@echo "$(CYAN)API: http://localhost:8000$(RESET)"
	@echo "$(CYAN)Docs: http://localhost:8000/docs$(RESET)"
	@echo "$(CYAN)LiveKit: ws://localhost:7880$(RESET)"
	@echo "$(YELLOW)Note: e-voice (STT+TTS) at port $(EVOICE_EXT_PORT) — docker start evoice$(RESET)"

infra-down:
	@echo "$(YELLOW)=== Stopping all services ===$(RESET)"
	@docker compose -f $(COMPOSE_FILE) down
	@echo "$(GREEN)=== Services stopped ===$(RESET)"

logs:
	@docker compose -f $(COMPOSE_FILE) logs -f api

# -----------------------------------------------------------------------------
# Local Development
# -----------------------------------------------------------------------------

# Service ports (matching e-core registry defaults)
REDIS_EXT_PORT   ?= 45000
LIVEKIT_EXT_PORT ?= 7880
EVOICE_EXT_PORT  ?= 45140

run: _ensure-deps
	@echo "$(GREEN)=== Starting Agent Server (session=$(SESSION)) ===$(RESET)"
	@DEFAULT_SESSION=$(SESSION) uv run python -m e_agents.rtc.app dev

console: _ensure-deps
	@echo "$(GREEN)=== Starting Console Mode (session=$(SESSION)) ===$(RESET)"
	@DEFAULT_SESSION=$(SESSION) uv run python -m e_agents.rtc.app console

_ensure-deps:
	@fail=false; \
	for pair in "$(REDIS_EXT_PORT):redis" "$(LIVEKIT_EXT_PORT):livekit"; do \
		port=$${pair%%:*}; svc=$${pair##*:}; \
		if nc -z localhost $$port 2>/dev/null; then \
			echo "$(GREEN)  ✓ $$svc (port $$port)$(RESET)"; \
		else \
			echo "$(YELLOW)  ✗ $$svc (port $$port) — starting via compose$(RESET)"; \
			docker compose -f $(COMPOSE_FILE) up -d $$svc; \
		fi; \
	done; \
	if nc -z localhost $(EVOICE_EXT_PORT) 2>/dev/null; then \
		echo "$(GREEN)  ✓ evoice (port $(EVOICE_EXT_PORT))$(RESET)"; \
	else \
		fail=true; \
		echo "$(RED)  ✗ evoice (port $(EVOICE_EXT_PORT)) — run: docker start evoice$(RESET)"; \
	fi; \
	if [ "$$fail" = true ]; then \
		echo "$(RED)=== Missing services — see above ===$(RESET)"; \
		exit 1; \
	fi; \
	echo "$(GREEN)=== All services running ===$(RESET)"

script: _ensure-media
	@$(if $(filter-out $@,$(MAKECMDGOALS)),,echo "$(RED)=== Usage: make script handoffs ===$(RESET)" && exit 1)
	@echo "$(GREEN)=== Running scripts/$(filter-out $@,$(MAKECMDGOALS)).py ===$(RESET)"
	@uv run scripts/$(filter-out $@,$(MAKECMDGOALS)).py

_ensure-media:
	@if nc -z localhost $(EVOICE_EXT_PORT) 2>/dev/null; then \
		echo "$(GREEN)  ✓ evoice (port $(EVOICE_EXT_PORT))$(RESET)"; \
	else \
		echo "$(RED)  ✗ evoice (port $(EVOICE_EXT_PORT)) — run: docker start evoice$(RESET)"; \
		exit 1; \
	fi

# Join variables
IDENTITY ?= user
ROOM ?= test-room
TTL ?= 60

join:
	@echo "$(GREEN)=== Joining room=$(ROOM) as identity=$(IDENTITY) ===$(RESET)"
	@uv run cli join --room $(ROOM) --identity $(IDENTITY) --ttl $(TTL)

token:
	@uv run cli token generate --identity $(IDENTITY) --room $(ROOM) --ttl $(TTL)

stt:
	@echo "$(GREEN)=== STT live mic → e-voice WS (Ctrl+C to stop) ===$(RESET)"
	@command -v ffmpeg >/dev/null 2>&1 || { echo "$(RED)ffmpeg not found$(RESET)"; exit 1; }
	@command -v websocat >/dev/null 2>&1 || { echo "$(RED)websocat not found$(RESET)"; exit 1; }
	@nc -z localhost $(EVOICE_EXT_PORT) 2>/dev/null || { echo "$(RED)e-voice not running on port $(EVOICE_EXT_PORT)$(RESET)"; exit 1; }
	@ffmpeg -loglevel quiet -f alsa -i default -ac 1 -ar 16000 -f s16le - | websocat --binary "ws://localhost:$(EVOICE_EXT_PORT)/v1/audio/transcriptions?language=$(LANGUAGE)"

# -----------------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------------
clean:
	@echo "$(YELLOW)=== Cleaning cache and artifacts ===$(RESET)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf dist/ build/ *.egg-info/
	@echo "$(GREEN)=== Clean complete ===$(RESET)"

# Catch-all: swallow extra positional args (used by `make script <name>`)
%:
	@:
