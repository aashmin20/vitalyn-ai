#!/bin/zsh
# Start the VITALYN backend for a demo: frees ports 8000/8443, then runs uvicorn.
# The backend itself checks (and if needed requests) macOS Camera permission at startup.
# Run it in a normal terminal tab (Terminal app or the Claude app's Terminal panel), not VS Code.
kill $(lsof -nti tcp:8000 -i tcp:8443) 2>/dev/null
sleep 1
cd "$(dirname "$0")/../backend" || exit 1
exec python3 -m uvicorn main:app --host 127.0.0.1 --port 8000
