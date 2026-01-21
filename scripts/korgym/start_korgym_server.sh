#!/bin/bash
# KORGym Game Server Launcher
# This script helps start the KORGym game server

set -e

GAME_NAME="${1:-8-word_puzzle}"
GAME_PORT="${2:-8775}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KORGYM_ROOT="${PROJECT_ROOT}/KORGym"

echo "=========================================="
echo "KORGym Game Server Launcher"
echo "=========================================="
echo "Game: ${GAME_NAME}"
echo "Port: ${GAME_PORT}"
echo ""

# Check if KORGym directory exists
if [ ! -d "${KORGYM_ROOT}" ]; then
    echo "❌ KORGym directory not found at: ${KORGYM_ROOT}"
    echo "Please ensure KORGym is cloned in the project root"
    exit 1
fi

# Check if game directory exists
GAME_DIR="${KORGYM_ROOT}/game_lib/${GAME_NAME}"
if [ ! -d "${GAME_DIR}" ]; then
    echo "❌ Game directory not found: ${GAME_DIR}"
    echo ""
    echo "Available games:"
    ls -1 "${KORGYM_ROOT}/game_lib/" | grep "^[0-9]" | head -20
    exit 1
fi

# Check if game_lib.py exists
if [ ! -f "${GAME_DIR}/game_lib.py" ]; then
    echo "❌ game_lib.py not found in ${GAME_DIR}"
    exit 1
fi

echo "Starting game server..."
echo "Game directory: ${GAME_DIR}"
echo ""
echo "Access the API docs at: http://localhost:${GAME_PORT}/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo "=========================================="
echo ""

cd "${GAME_DIR}"
python game_lib.py -p ${GAME_PORT}

