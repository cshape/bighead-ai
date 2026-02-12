# Big Head

Play Big Head online with an AI host and dynamically-generated game boards. Supports multiple concurrent games via shareable game codes.

**Stack:** FastAPI, React/Vite, WebSockets, Inworld AI (LLM + TTS)

## Setup

```bash
pip install -r requirements.txt
npm install   # installs frontend deps

cp .env.example .env   # add your INWORLD_API_KEY
```

## Development

Run the backend and frontend dev server together:

```bash
npm run dev
```

Or run them separately:

```bash
npm run dev:backend   # backend with hot reload on :8000
npm run dev:frontend  # Vite dev server on :5173
```

## Production (local)

Build the frontend and serve everything from the backend:

```bash
npm run build && npm start
```

The app will be available at `http://localhost:8000`.

## Deploy to Render

1. Push your repo to GitHub
2. In Render, click **New > Blueprint** and connect your repo
3. Render auto-detects `render.yaml` and configures the service
4. Add your `INWORLD_API_KEY` in the Render dashboard under Environment

The blueprint (`render.yaml`) handles the rest: installs Python + Node deps, builds the frontend, and starts uvicorn.

## Tests

```bash
cd frontend && npm run test:e2e
```
