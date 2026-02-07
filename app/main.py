import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Centralized logging — must come before other app imports
from .utils.logging_config import setup_logging
setup_logging()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
from pathlib import Path
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

from .utils.file_loader import BoardFactory
from .models.board import Board
from .websockets.connection_manager import ConnectionManager
from .websockets.handlers import router as ws_router, init_handlers
from .services.game_service import GameService
from .services.game_manager import GameManager
from .services.chat_manager import ChatManager

# Try to import routers
try:
    from .routes import admin_routes
    has_admin_routes = True
except ImportError:
    has_admin_routes = False
    logger.warning("Admin routes not found, skipping")

try:
    from .routes import board_routes
    has_board_routes = True
except ImportError:
    has_board_routes = False
    logger.warning("Board routes not found, skipping")

try:
    from .routes import game_routes
    has_game_routes = True
except ImportError:
    has_game_routes = False
    logger.warning("Game routes not found, skipping")

app = FastAPI(title="Big Head")

# CORS configuration from environment
frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")
cors_origins = [
    frontend_url,
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
]

# Add any additional origins from environment (comma-separated)
additional_origins = os.environ.get("CORS_ORIGINS", "")
if additional_origins:
    cors_origins.extend([o.strip() for o in additional_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create static directory if it doesn't exist
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)
static_audio_dir = static_dir / "audio"
static_audio_dir.mkdir(exist_ok=True)

# Mount static files directory for existing static content
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Initialize connection manager and services
connection_manager = ConnectionManager()
game_service = GameService(connection_manager)
game_manager = GameManager()
chat_manager = ChatManager(connection_manager)
board_factory = BoardFactory()
board = board_factory.initialize()

# Wire up game manager to game service
game_service.set_game_manager(game_manager)

# Store in app state for access in routes
app.state.connection_manager = connection_manager
app.state.game_service = game_service
app.state.game_manager = game_manager
app.state.chat_manager = chat_manager

# Wire up WebSocket message handlers
init_handlers(game_service, game_manager, connection_manager, chat_manager)


@app.websocket("/ws/{game_code}")
async def websocket_game_endpoint(websocket: WebSocket, game_code: str, player_name: str = None):
    """WebSocket endpoint for a specific game."""
    logger.debug(f"New WebSocket connection request for game {game_code}, player_name={player_name}")

    # Find the game
    game = await game_manager.get_game_by_code(game_code)
    if not game:
        await websocket.close(code=4004, reason="Game not found")
        return

    try:
        # Connect and join the game room
        client_id = await connection_manager.connect(websocket, game_id=game.game_id, player_name=player_name)
        game.add_client(client_id)

        # If player_name provided (HTTP-joined player connecting), link their game state entry
        if player_name:
            existing_contestant = game.state.get_contestant_by_name(player_name)
            if existing_contestant:
                # Update the contestant's key to the new websocket client_id
                logger.info(f"Linking websocket {client_id} to player '{player_name}'")
                game.state.update_contestant_key(player_name, client_id)

        # Send current game state
        await connection_manager.send_personal_message(
            websocket,
            "com.sc2ctl.bighead.game_state",
            game.get_state_for_client()
        )

        # Send chat history for this game
        await chat_manager.send_chat_history(websocket, game_id=game.game_id)

        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                logger.debug(f"Received WebSocket message from {client_id}: {data}")

                await ws_router.dispatch(websocket, client_id, data, game_id=game.game_id, game=game)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode WebSocket message: {e}")
                continue

    except WebSocketDisconnect:
        game.remove_client(client_id)
        await connection_manager.disconnect(websocket)
        logger.info(f"Client {client_id} disconnected from game {game_code}")

        # Broadcast updated player list
        await connection_manager.broadcast_to_room(
            game.game_id,
            "com.sc2ctl.bighead.player_list",
            {"players": game.state.get_players_dict()}
        )
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {e}")
        if client_id:
            game.remove_client(client_id)
        await connection_manager.disconnect(websocket)



# Routes for web pages - Define all HTTP routes before mounting static files
@app.get("/")
async def index():
    return FileResponse("frontend/dist/index.html")

@app.get("/admin")
async def admin():
    return FileResponse("frontend/dist/index.html")

@app.get("/board")
async def view_board():
    return FileResponse("frontend/dist/index.html")

@app.get("/play/{username}")
async def play(username: str):
    return FileResponse("frontend/dist/index.html")

@app.get("/contestants")
async def contestants():
    return FileResponse("frontend/dist/index.html")

# New routes for multi-game support
@app.get("/game/{code}")
async def game_page(code: str):
    """Serve the game page for a specific game code."""
    return FileResponse("frontend/dist/index.html")

@app.get("/game/{code}/lobby")
async def lobby_page(code: str):
    """Serve the lobby page for a specific game code."""
    return FileResponse("frontend/dist/index.html")

@app.get("/api/boards")
async def get_available_boards():
    """Get list of available board files from game_data directory"""
    boards_dir = Path("game_data")
    if not boards_dir.exists():
        boards_dir = Path("app/game_data")

    if boards_dir.exists():
        board_files = [f.stem for f in boards_dir.glob("*.json")]
        return {"boards": board_files}

    return {"boards": []}

@app.post("/api/load-board")
async def load_board(board_request: dict):
    """Load a board for a specific game. Requires game_id."""
    board_name = board_request.get("board")
    game_id = board_request.get("game_id")

    if not board_name:
        raise HTTPException(status_code=400, detail="Board name is required")

    if not game_id:
        raise HTTPException(status_code=400, detail="game_id is required")

    try:
        game = await game_manager.get_game_by_id(game_id)
        if not game:
            raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

        new_board = board_factory.load_board(board_name)
        game.board = new_board
        await game_service.send_categories(game_id)
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading board: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/play-audio")
async def play_audio(request: dict):
    """API endpoint for AI Host to request audio playback on all clients."""
    audio_url = request.get("audio_url")
    if not audio_url:
        raise HTTPException(status_code=400, detail="audio_url is required")

    game_id = request.get("game_id")
    if not game_id:
        raise HTTPException(status_code=400, detail="game_id is required")

    logger.debug(f"Broadcasting audio playback request: {audio_url}")

    await connection_manager.broadcast_message(
        "com.sc2ctl.bighead.play_audio",
        {"url": audio_url},
        game_id=game_id
    )

    return {"status": "success", "message": "Audio broadcast initiated"}

# Include routers
if has_admin_routes:
    app.include_router(admin_routes.router)
if has_board_routes:
    app.include_router(board_routes.router)
if has_game_routes:
    app.include_router(game_routes.router)

# Add favicon route to prevent 404 errors
@app.get("/favicon.ico")
async def favicon():
    favicon_path = Path("frontend/dist/favicon.ico")
    if favicon_path.exists():
        return FileResponse(str(favicon_path), media_type="image/x-icon")
    from starlette.responses import Response
    return Response(status_code=204)

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("Starting application...")

    # Start the game manager
    await game_manager.start()

    logger.info("Application startup completed")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down application...")
    await game_manager.stop()
    logger.info("Application shutdown completed")

# Mount frontend static assets AFTER all API and WebSocket routes are defined
app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")

# Serve frontend in production if SERVE_FRONTEND is set
if os.environ.get("SERVE_FRONTEND"):
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")

# Run with: uvicorn app.main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
