#!/bin/bash
# ==============================================================================
# DocUrgent 24/7 — Instant Emergency Telehealth Platform
# One-click desktop launcher for macOS
# ==============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR/docurgent"

PORT=8095
if lsof -Pi :8096 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    PORT=8096
elif ! lsof -Pi :8095 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "Starting DocUrgent 24/7 server..."
    PY_BIN="/usr/bin/python3"
    if [ ! -x "$PY_BIN" ]; then PY_BIN="python3"; fi
    nohup $PY_BIN server.py > /dev/null 2>&1 &
    sleep 1.5
    if lsof -Pi :8096 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        PORT=8096
    fi
fi

URL="http://localhost:${PORT}"

echo "========================================================"
echo "  🏥 DocUrgent 24/7 — Emergency Telehealth Network"
echo "  Instant Doctor Video Consult & Rapid Triage"
echo "========================================================"
echo "  Opening Application in Default Browser: ${URL}"
echo "========================================================"

open "${URL}"
