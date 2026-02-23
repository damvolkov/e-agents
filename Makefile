# =============================================================================
# e-template-agents Makefile
# =============================================================================
PROJECT ?= e-template-agents
VERSION ?= latest
DEBUG ?= true
ENVIRONMENT ?= DEV
PACKAGE ?= src/e_template_agents
SESSION ?= double_loop

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

.PHONY: help install sync lock lint format type test \
        infra infra-down build logs \
        run console join token clean

# -----------------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------------
help:
	@echo "$(BOLD)$(BLUE)e-template-agents$(RESET) - Multi-agent Voice AI Template"
	@echo ""
	@echo "$(BOLD)Setup:$(RESET)"
	@echo "  $(GREEN)make install$(RESET)      Install uv, dependencies, and pre-commit hooks"
	@echo "  $(GREEN)make sync$(RESET)         Sync dependencies from lockfile"
	@echo "  $(GREEN)make lock$(RESET)         Update lockfile with current dependencies"
	@echo ""
	@echo "$(BOLD)Infrastructure:$(RESET)"
	@echo "  $(GREEN)make infra$(RESET)        Start all services (API + STT/TTS/LiveKit)"
	@echo "  $(GREEN)make infra-down$(RESET)   Stop all infrastructure services"
	@echo "  $(GREEN)make logs$(RESET)         Follow API container logs"
	@echo "  $(GREEN)make build$(RESET)        Build Docker image"
	@echo ""
	@echo "$(BOLD)Local Development:$(RESET)"
	@echo "  $(GREEN)make run$(RESET)          Start agent server (API runs in background)"
	@echo "  $(GREEN)make console$(RESET)      Start agent in console mode (local testing)"
	@echo "  $(GREEN)make join$(RESET)         Join a room as participant"
	@echo "  $(GREEN)make token$(RESET)        Generate LiveKit access token"
	@echo ""
	@echo "$(BOLD)Variables:$(RESET)"
	@echo "  $(CYAN)SESSION$(RESET)=$(SESSION)    Session type (double_loop)"
	@echo "  $(CYAN)ROOM$(RESET)=test-room      Room name for join/token"
	@echo "  $(CYAN)IDENTITY$(RESET)=user       Participant identity"
	@echo "  $(CYAN)TTL$(RESET)=60              Token TTL in minutes"
	@echo ""
	@echo "$(BOLD)Quality:$(RESET)"
	@echo "  $(GREEN)make lint$(RESET)         Run ruff linter with auto-fix"
	@echo "  $(GREEN)make format$(RESET)       Format code with ruff"
	@echo "  $(GREEN)make type$(RESET)         Run type checker"
	@echo "  $(GREEN)make test$(RESET)         Run unit tests"
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
	@uv run pytest tests/unit -v
	@echo "$(GREEN)=== Tests complete ===$(RESET)"

# -----------------------------------------------------------------------------
# Infrastructure (Docker)
# -----------------------------------------------------------------------------
build:
	@echo "$(GREEN)=== Building Docker image ===$(RESET)"
	@docker compose -f $(COMPOSE_FILE) build api
	@echo "$(GREEN)=== Build complete ===$(RESET)"

infra:
	@echo "$(GREEN)=== Starting all services ===$(RESET)"
	@docker compose -f $(COMPOSE_FILE) up -d redis livekit stt tts api
	@echo "$(GREEN)=== Services ready ===$(RESET)"
	@echo "$(CYAN)API: http://localhost:8000$(RESET)"
	@echo "$(CYAN)Docs: http://localhost:8000/docs$(RESET)"
	@echo "$(CYAN)LiveKit: ws://localhost:7880$(RESET)"

infra-down:
	@echo "$(YELLOW)=== Stopping all services ===$(RESET)"
	@docker compose -f $(COMPOSE_FILE) down
	@echo "$(GREEN)=== Services stopped ===$(RESET)"

logs:
	@docker compose -f $(COMPOSE_FILE) logs -f api

# -----------------------------------------------------------------------------
# Local Development
# -----------------------------------------------------------------------------
run:
	@echo "$(GREEN)=== Starting Agent Server (session=$(SESSION)) ===$(RESET)"
	@uv run python -m e_template_agents run --session $(SESSION)

console:
	@echo "$(GREEN)=== Starting Console Mode (session=$(SESSION)) ===$(RESET)"
	@uv run python -m e_template_agents console --session $(SESSION)

# Join variables
IDENTITY ?= user
ROOM ?= test-room
TTL ?= 60

join:
	@echo "$(GREEN)=== Joining room=$(ROOM) as identity=$(IDENTITY) ===$(RESET)"
	@uv run python -m e_template_agents join --room $(ROOM) --identity $(IDENTITY) --ttl $(TTL)

token:
	@uv run python -m e_template_agents token generate --identity $(IDENTITY) --room $(ROOM) --ttl $(TTL)

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
