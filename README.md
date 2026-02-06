# Jeopardy AI

Play Jeopardy online with an AI host and dynamically-generated game boards. Supports multiple concurrent games via shareable game codes.

**Stack:** FastAPI, React/Vite, WebSockets, Inworld AI (LLM + TTS)

## Setup

```bash
pip install -r app/requirements.txt
npm install   # installs frontend deps

cp .env.example .env   # add your INWORLD_API_KEY
```

## Development

```bash
# Backend
npm start

# Frontend (separate terminal)
npm run dev   # from frontend/
```

## Tests

```bash
cd frontend && npm run test:e2e
```

## Play Online

You can share your game with friends using [ngrok](https://ngrok.com/):

```bash
npm run build && npm start
ngrok http 8000
```
