# Configuration
# Settings are now read from ~/.config/katagollum.yaml (user config)
# or config.yaml.default (default config in project root)
# See config.yaml.default for available options

# Directories
BACKEND_DIR := web_backend
FRONTEND_DIR := web_frontend
PROJECT_DIR := $(CURDIR)

# Python venv
VENV_PATH := $(PROJECT_DIR)/.venv
PYTHON := $(VENV_PATH)/bin/python
PIP := $(VENV_PATH)/bin/pip

.PHONY: help install migrate run-all run-mcp run-backend run-frontend down check-katago clear-cache

help:
	@echo "Trash Talk Go Bot - Available commands:"
	@echo ""
	@echo "  make install          - Install all dependencies"
	@echo "  make migrate          - Run database migrations"
	@echo "  make run-mcp          - Start KataGo MCP server"
	@echo "  make run-backend      - Start Django backend"
	@echo "  make run-frontend     - Start Next.js frontend"
	@echo "  make run-ollama       - Start Ollama server"
	@echo "  make up               - Start all servers (MCP, backend, frontend)"
	@echo "  make down             - Stop all servers and clear cache"
	@echo "  make clear-cache      - Clear Python __pycache__ directories"
	@echo "  make check-katago     - Check if KataGo MCP is running"
	@echo ""

install:
	@echo "Installing Python dependencies..."
	@$(PIP) install django djangorestframework django-cors-headers httpx pyyaml
	@echo ""
	@echo "Installing frontend dependencies..."
	@cd $(FRONTEND_DIR) && npm install
	@echo ""
	@echo "Done! Run 'make migrate' then 'make up'"

migrate:
	@echo "Running database migrations..."
	@cd $(BACKEND_DIR) && $(PYTHON) manage.py migrate
	@echo "Done!"

run-mcp:
	@if lsof -ti:3001 >/dev/null 2>&1; then echo "KataGo MCP already running on port 3001"; else \
		echo "Starting KataGo MCP server on port 3001..."; \
		$(PYTHON) -m src.katago_mcp.server --transport sse --port 3001 & \
		sleep 2; \
		echo "KataGo MCP server started on http://localhost:3001"; \
	fi

run-backend:
	@if lsof -ti:8000 >/dev/null 2>&1; then echo "Django backend already running on port 8000"; else \
		echo "Starting Django backend on port 8000..."; \
		cd $(BACKEND_DIR) && $(PYTHON) manage.py runserver 8000 & \
		sleep 2; \
		echo "Django backend started on http://localhost:8000"; \
	fi

run-frontend:
	@if lsof -ti:3000 >/dev/null 2>&1; then echo "Next.js frontend already running on port 3000"; else \
		echo "Starting Next.js frontend on port 3000..."; \
		cd $(FRONTEND_DIR) && npm run dev & \
		sleep 5; \
		echo "Next.js frontend started on http://localhost:3000"; \
	fi

run-ollama:
	@if pgrep -f "ollama serve" >/dev/null 2>&1; then echo "Ollama already running"; else \
		echo "Starting Ollama server..."; \
		ollama serve & \
		sleep 2; \
		echo "Ollama server started"; \
	fi

up: run-ollama run-mcp run-backend run-frontend
	@echo ""
	@echo "=========================================="
	@echo "All servers started!"
	@echo "=========================================="
	@echo "MCP Server:   http://localhost:3001"
	@echo "Django API:   http://localhost:8000"
	@echo "Frontend:     http://localhost:3000"
	@echo ""
	@echo "Press Ctrl+C to stop all servers"
	@echo "=========================================="
	@wait

clear-cache:
	@echo "Clearing Python cache..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cache cleared"

down: clear-cache
	@echo "Stopping all servers..."
	@$(PROJECT_DIR)/scripts/stop-services.sh

kill-all:
	@echo "Force killing all processes..."
	@killall -9 node python katago 2>/dev/null || true
	@echo "Done"

check-katago:
	@curl -s http://localhost:3001/list_tools 2>/dev/null && echo " - KataGo MCP is running" || echo "KataGo MCP is NOT running (run 'make run-mcp')"

# Development shortcuts
dev: up
	@:

build-frontend:
	@cd $(FRONTEND_DIR) && npm run build

test-backend:
	@cd $(BACKEND_DIR) && $(PYTHON) manage.py test

shell-backend:
	@cd $(BACKEND_DIR) && $(PYTHON) manage.py shell
