#!/bin/bash
set -e

echo "Stopping all servers..."

# Kill by port
fuser -k 3000/tcp 2>/dev/null || true
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 3001/tcp 2>/dev/null || true

# Kill by process name (exclude this script and parent shell)
current_pid=$$
parent_pid=$$

pids=$(pgrep -f "katago_mcp" 2>/dev/null | grep -v -E "^($current_pid|$parent_pid)$")
for pid in $pids; do kill -9 $pid 2>/dev/null || true; done

pids=$(pgrep -f "manage.py runserver" 2>/dev/null | grep -v -E "^($current_pid|$parent_pid)$")
for pid in $pids; do kill -9 $pid 2>/dev/null || true; done

pids=$(pgrep -f "ollama serve" 2>/dev/null | grep -v -E "^($current_pid|$parent_pid)$")
for pid in $pids; do kill -9 $pid 2>/dev/null || true; done

pids=$(pgrep -f "next-server" 2>/dev/null | grep -v -E "^($current_pid|$parent_pid)$")
for pid in $pids; do kill -9 $pid 2>/dev/null || true; done

pids=$(pgrep -f "node.*next" 2>/dev/null | grep -v -E "^($current_pid|$parent_pid)$")
for pid in $pids; do kill -9 $pid 2>/dev/null || true; done

sleep 1
echo "All servers stopped"
