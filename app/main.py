import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional
import json
import asyncio
import logging
from pathlib import Path
import subprocess
from fastapi.responses import FileResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from .utils.file_loader import BoardFactory
from .models.board import Board
from .websockets.connection_manager import ConnectionManager
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

app = FastAPI(title="Jeopardy Game")

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


async def handle_websocket_message(
    websocket: WebSocket,
    client_id: str,
    data: dict,
    game_id: Optional[str] = None
):
    """Handle incoming WebSocket messages, optionally scoped to a game."""
    topic = data.get('topic')
    payload = data.get('payload', {})

    # Get game instance if we have a game_id
    game = None
    if game_id:
        game = await game_manager.get_game_by_id(game_id)

    if topic == 'com.sc2ctl.jeopardy.register_player':
        name = payload.get('name')
        preferences = payload.get('preferences', '')
        logger.info(f"Registering player: {name} with preferences: {preferences}")

        if game:
            # Multi-game: register in specific game
            # Create a database player record (like HTTP join does)
            player_data = await game_manager.player_repo.create_player(
                game_id=game.game_id,
                name=name,
                preferences=preferences,
                websocket_id=client_id,
            )
            player_id = player_data["id"]

            # Register in game state using player_id as key (consistent with HTTP join)
            success = game.state.register_contestant(player_id, name)
            if success:
                game.add_client(client_id)

                # Store preferences in the game's AI host state manager
                if preferences and hasattr(game.ai_host, 'game_state_manager'):
                    game.ai_host.game_state_manager.add_player_preference(name, preferences)

                # If this is the first player, make them the host
                if game.host_player_id is None:
                    game.host_player_id = player_id
                    await game_manager.game_repo.set_host_player(game.game_id, player_id)

                await connection_manager.send_personal_message(
                    websocket,
                    "com.sc2ctl.jeopardy.register_player_response",
                    {"success": True, "name": name, "player_id": player_id, "is_host": game.host_player_id == player_id}
                )

                # Get player preferences for broadcast
                player_prefs = {}
                if hasattr(game.ai_host, 'game_state_manager'):
                    player_prefs = game.ai_host.game_state_manager.player_preferences

                # Build players dict with preferences
                players_with_prefs = {
                    c.name: {
                        "score": c.score,
                        "preferences": player_prefs.get(c.name, "")
                    }
                    for c in game.state.contestants.values()
                }

                # Broadcast updated player list to game room
                await connection_manager.broadcast_to_room(
                    game_id,
                    "com.sc2ctl.jeopardy.player_list",
                    {"players": players_with_prefs}
                )
                # Check if game is ready
                if game.can_start():
                    await connection_manager.broadcast_to_room(
                        game_id,
                        "com.sc2ctl.jeopardy.game_ready",
                        {"ready": True}
                    )
        else:
            # Legacy: single-game mode
            success = await game_service.register_player(websocket, name, preferences)
            if success:
                await game_service.connection_manager.send_personal_message(
                    websocket,
                    "com.sc2ctl.jeopardy.register_player_response",
                    {"success": True, "name": name}
                )

    elif topic == 'com.sc2ctl.jeopardy.select_board':
        board_id = payload.get('boardId') or payload.get('board_id')
        logger.info(f"Selecting board: {board_id}")

        if game:
            # Load board for specific game
            await game_service.select_board(board_id, game_id=game_id)
        else:
            await game_service.select_board(board_id)

    elif topic == game_service.QUESTION_DISPLAY_TOPIC:
        category = payload.get('category')
        value = payload.get('value')
        logger.info(f"Displaying question: {category} - ${value}")
        await game_service.display_question(category, value, game_id=game_id)
        await game_service.change_buzzer_status(True, game_id=game_id)

    elif topic == 'com.sc2ctl.jeopardy.daily_double':
        category = payload.get('category')
        value = payload.get('value')
        logger.info(f"Daily double selected: {category} - ${value}")
        await game_service.display_question(category, value, game_id=game_id)

    elif topic == game_service.BUZZER_TOPIC:
        timestamp = payload.get('timestamp')
        await game_service.handle_buzz(websocket, timestamp, game_id=game_id)

    elif topic == game_service.QUESTION_ANSWER_TOPIC:
        correct = payload.get('correct')
        contestant = payload.get('contestant')
        logger.info(f"Answering question: {'correct' if correct else 'incorrect'}")
        await game_service.answer_question(correct, contestant, game_id=game_id)

    elif topic == game_service.QUESTION_DISMISS_TOPIC:
        await game_service.dismiss_question(game_id=game_id)

    elif topic == game_service.BOARD_INIT_TOPIC:
        await game_service.send_categories(game_id=game_id)

    elif topic == game_service.DAILY_DOUBLE_BET_TOPIC:
        contestant = payload.get('contestant')
        bet = payload.get('bet')
        logger.info(f"Daily double bet from {contestant}: ${bet}")
        await game_service.handle_daily_double_bet(contestant, bet, game_id=game_id)

    elif topic == 'com.sc2ctl.jeopardy.chat_message':
        username = payload.get('username', 'Anonymous')
        message_text = payload.get('message', '')

        if game_id:
            await chat_manager.handle_message(username, message_text, game_id=game_id)
        else:
            await chat_manager.handle_message(username, message_text)

        await game_service.handle_chat_message(username, message_text, game_id=game_id)

    elif topic == 'com.sc2ctl.jeopardy.audio_complete':
        audio_id = payload.get('audio_id')
        if audio_id:
            logger.info(f"Received audio completion via WebSocket: {audio_id}")
            await game_service.handle_audio_completed(audio_id, game_id=game_id)
        else:
            logger.warning("Received audio completion message without audio_id")

    elif topic == 'com.sc2ctl.jeopardy.start_ai_game':
        logger.info("Starting AI game...")
        num_players = payload.get("num_players", 3)
        headless = payload.get("headless", True)

        try:
            project_root = Path(__file__).parent.parent
            standalone_script = project_root / "standalone_ai_player.py"
            os.chmod(standalone_script, 0o755)
            headless_arg = "true" if headless else "false"
            cmd = [str(standalone_script), str(num_players), headless_arg]

            logger.info(f"Launching standalone AI player with: {' '.join(cmd)}")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(project_root)
            )

            await connection_manager.send_personal_message(
                websocket,
                "com.sc2ctl.jeopardy.ai_game_started",
                {"status": "success"}
            )
            logger.info("AI game started successfully")
        except Exception as e:
            logger.error(f"Failed to start standalone AI player: {e}")
            await connection_manager.send_personal_message(
                websocket,
                "com.sc2ctl.jeopardy.ai_game_started",
                {"status": "error", "message": f"Failed to start AI game: {str(e)}"}
            )

    elif topic == 'com.sc2ctl.jeopardy.stop_ai_game':
        logger.info("Stopping AI game...")
        try:
            if os.name == 'posix':
                subprocess.run(["pkill", "-f", "standalone_ai_player.py"], check=False)
            else:
                subprocess.run(["taskkill", "/f", "/im", "python.exe"], check=False)

            await connection_manager.send_personal_message(
                websocket,
                "com.sc2ctl.jeopardy.ai_game_stopped",
                {"status": "success"}
            )
            logger.info("AI game stopped successfully")
        except Exception as e:
            logger.error(f"Failed to stop AI game: {e}")
            await connection_manager.send_personal_message(
                websocket,
                "com.sc2ctl.jeopardy.ai_game_stopped",
                {"status": "error", "message": f"Failed to stop AI game: {str(e)}"}
            )

    elif topic == 'com.sc2ctl.jeopardy.start_ai_host':
        logger.info("Starting AI host...")
        try:
            await connection_manager.send_personal_message(
                websocket,
                "com.sc2ctl.jeopardy.ai_host_started",
                {"status": "success"}
            )
            logger.info("AI host started successfully")
        except Exception as e:
            logger.error(f"Failed to start AI host: {e}")
            await connection_manager.send_personal_message(
                websocket,
                "com.sc2ctl.jeopardy.ai_host_started",
                {"status": "error", "message": f"Failed to start AI host: {str(e)}"}
            )

    elif topic == 'com.sc2ctl.jeopardy.start_game':
        # Host requesting to start the game
        if game:
            player_id = payload.get('player_id')
            if game.host_player_id == player_id or game.is_host(player_id):
                success = await game_manager.start_game(game_id, game_service)
                if success:
                    await connection_manager.broadcast_to_room(
                        game_id,
                        "com.sc2ctl.jeopardy.game_started",
                        {"status": "started"}
                    )


# New WebSocket endpoint with game code
@app.websocket("/ws/{game_code}")
async def websocket_game_endpoint(websocket: WebSocket, game_code: str):
    """WebSocket endpoint for a specific game."""
    logger.debug(f"New WebSocket connection request for game {game_code}")

    # Find the game
    game = await game_manager.get_game_by_code(game_code)
    if not game:
        await websocket.close(code=4004, reason="Game not found")
        return

    try:
        # Connect and join the game room
        client_id = await connection_manager.connect(websocket, game_id=game.game_id)
        game.add_client(client_id)

        # Send current game state
        await connection_manager.send_personal_message(
            websocket,
            "com.sc2ctl.jeopardy.game_state",
            game.get_state_for_client()
        )

        # Send chat history for this game
        await chat_manager.send_chat_history(websocket, game_id=game.game_id)

        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                logger.debug(f"Received WebSocket message from {client_id}: {data}")

                await handle_websocket_message(websocket, client_id, data, game_id=game.game_id)

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
            "com.sc2ctl.jeopardy.player_list",
            {"players": game.state.get_players_dict()}
        )
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {e}")
        if client_id:
            game.remove_client(client_id)
        await connection_manager.disconnect(websocket)


# Legacy WebSocket endpoint (for backward compatibility)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Legacy WebSocket endpoint without game code."""
    logger.debug("New WebSocket connection request (legacy)")
    try:
        client_id = await connection_manager.connect(websocket)
        await game_service.send_game_state(websocket)
        await chat_manager.send_chat_history(websocket)

        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                logger.debug(f"Received WebSocket message from {client_id}: {data}")

                await handle_websocket_message(websocket, client_id, data, game_id=None)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode WebSocket message: {e}")
                continue

    except WebSocketDisconnect:
        await connection_manager.disconnect(websocket)
        logger.info(f"Client disconnected")
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {e}")
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
    board_name = board_request.get("board")
    if not board_name:
        raise HTTPException(status_code=400, detail="Board name is required")

    try:
        new_board = board_factory.load_board(board_name)
        game_service.board = new_board
        await game_service.send_categories()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error loading board: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/play-audio")
async def play_audio(request: dict):
    """API endpoint for AI Host to request audio playback on all clients."""
    audio_url = request.get("audio_url")
    if not audio_url:
        raise HTTPException(status_code=400, detail="audio_url is required")

    logger.info(f"Broadcasting audio playback request: {audio_url}")

    # Get game_id if provided for room-scoped broadcast
    game_id = request.get("game_id")

    await connection_manager.broadcast_message(
        "com.sc2ctl.jeopardy.play_audio",
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
    return FileResponse("frontend/dist/favicon.ico", media_type="image/x-icon")

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("Starting application...")

    # Start the game manager
    await game_manager.start()

    # Initialize the legacy game service and start the AI host
    await game_service.startup()

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
