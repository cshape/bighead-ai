# Big Head

A web app that lets players play Big Head against each other with an AI host. The backend (FastAPI + WebSockets) manages game state, generates boards via LLM, evaluates answers, and synthesizes the host's voice through Inworld AI. The frontend (React/Vite) renders the game board, buzzer, and chat. Multiple concurrent games are supported via shareable game codes.

## After Major Changes

Run the end-to-end tests to make sure nothing is broken. Kill any running backend server first (the test harness starts its own on port 8000):

```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null; cd frontend && npm run test:e2e
```
Check TODOs.md and update if necessary.

## Tech Stack

- **Backend**: Python, FastAPI, WebSockets (wsproto), Pydantic
- **Frontend**: React 19, Vite 6, React Router 7, vanilla CSS
- **AI**: Inworld API (LLM + TTS), OpenAI models (gpt-4o, gpt-4o-mini)
- **No database** — all game state is in-memory

## Dev Commands

```bash
# Install everything (frontend deps + root concurrently)
npm install

# Run both backend + frontend in parallel
npm run dev

# Run individually
npm run dev:backend    # uvicorn on :8000
npm run dev:frontend   # vite on :5173

# Build frontend for production
npm run build

# E2E tests (Puppeteer + Jest)
cd frontend && npm run test:e2e
```

## Environment

Copy `.env.example` to `.env`. Required: `INWORLD_API_KEY`. See `.env.example` for all options.

## Architecture

```
app/                          # FastAPI backend
├── main.py                   # App init, WebSocket endpoint, static serving
├── routes/                   # REST API (game create/join)
├── services/
│   ├── game_manager.py       # Multi-game singleton (creates/finds GameInstances)
│   ├── game_instance.py      # Per-game state container
│   ├── game_service.py       # Game orchestration logic
│   └── chat_manager.py       # Chat message handling
├── models/                   # Pydantic models (board, contestant, messages, etc.)
├── websockets/               # WS connection manager, message router, handlers
├── ai/
│   ├── host/                 # AI Host — game flow, buzzer, answer eval, audio, board ops
│   ├── board_generation/     # LLM-based board/clue generation
│   ├── utils/                # LLM client, TTS client, prompt manager
│   └── prompt_templates/     # Jinja2 templates for LLM prompts
└── utils/                    # Logging config

frontend/src/                 # React SPA
├── contexts/GameContext.jsx  # Centralized game state (reducer pattern)
├── hooks/                    # useWebSocket, useAudioPlayer
├── pages/                    # HomePage, LobbyPage, GamePage
├── components/               # GameBoard, Modals, ScoreBoard, Chat, Admin
└── styles/                   # CSS files (theme, layout, components)
```

## Key Patterns

- **Multi-game**: GameManager creates GameInstance objects keyed by 6-char codes
- **WebSocket flow**: Client connects to `/ws/{game_code}`, messages routed by type via MessageRouter
- **AI Host**: Async loop per game — monitors buzzer state, evaluates answers via LLM, generates TTS audio
- **Board generation**: LLM generates 5 categories + 25 clues from player preferences, streamed to frontend
- **TTS**: Inworld API, voice configurable, audio served as static files from `/static/audio/`

## Testing

- E2E only (Puppeteer/Jest): `frontend/tests/e2e/`
- No backend unit tests yet
- `TEST_MODE` env var enables simple string matching instead of LLM answer evaluation
