# Big Head

A web app that lets players play Big Head against each other with an AI host. The backend (FastAPI + WebSockets) manages game state, generates boards via LLM, evaluates answers, and synthesizes the host's voice through Inworld AI. The frontend (React/Vite) renders the game board, buzzer, and chat. Multiple concurrent games are supported via shareable game codes.

## After Major Changes

Run the end-to-end tests to make sure nothing is broken. Kill any running backend server first (the test harness starts its own on port 8000):

```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null; cd frontend && npm run test:e2e
```
Check TODOs.md and update if necessary.
