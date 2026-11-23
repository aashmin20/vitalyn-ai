#!/bin/zsh
# Start the VITALYN frontend on port 3000 (the only port the backend's CORS allows).
kill $(lsof -nti tcp:3000) 2>/dev/null
sleep 1
cd "$(dirname "$0")/../frontend" || exit 1
exec npm run dev -- --port 3000
