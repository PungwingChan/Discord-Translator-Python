#!/bin/bash
set -e

echo "======================================================"
echo "   🌸  Discord Translation Bot — Startup Script"
echo "======================================================"
echo ""

# ── Check Python 3 ────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ERR ] python3 not found. Please install Python 3.8+."
    exit 1
fi
echo "[OK  ] $(python3 --version)"

# ── Check pip3 ────────────────────────────────────────────────────────
if ! command -v pip3 &>/dev/null; then
    echo "[ERR ] pip3 not found. Please install pip."
    exit 1
fi

# ── Install dependencies ──────────────────────────────────────────────
echo ""
echo "[DEP ] Installing Python dependencies..."
pip3 install --quiet flask "discord.py>=2.0" requests
echo "[OK  ] Dependencies installed"
echo ""

# ── Port info ─────────────────────────────────────────────────────────
if   [ -n "$SERVER_PORT"    ]; then echo "[PORT] Using SERVER_PORT: $SERVER_PORT"
elif [ -n "$PORT"           ]; then echo "[PORT] Using PORT: $PORT"
elif [ -n "$APP_PORT"       ]; then echo "[PORT] Using APP_PORT: $APP_PORT"
elif [ -n "$ALLOCATED_PORT" ]; then echo "[PORT] Using ALLOCATED_PORT: $ALLOCATED_PORT"
else
    echo "[PORT] Using default port: 443"
    echo "[TIP ] Set environment variable PORT=<your_port> to override"
fi

echo ""
echo "[RUN ] Starting app.py ..."
echo ""

exec python3 app.py
