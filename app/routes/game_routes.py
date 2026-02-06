"""
Game routes for creating and joining games.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/games", tags=["games"])


class CreateGameResponse(BaseModel):
    """Response for game creation."""
    game_id: str
    code: str
    status: str


class JoinGameRequest(BaseModel):
    """Request body for joining a game."""
    player_name: str = Field(..., min_length=1, max_length=100)
    preferences: Optional[str] = None


class JoinGameResponse(BaseModel):
    """Response for joining a game."""
    game_id: str
    code: str
    player_id: str
    player_name: str
    is_host: bool
    status: str
    players: list


class GameStateResponse(BaseModel):
    """Response containing game state."""
    game_id: str
    code: str
    status: str
    players: list
    player_count: int
    can_start: bool
    host_player_id: Optional[str]


class StartGameRequest(BaseModel):
    """Request to start a game."""
    player_id: str  # Must be the host


@router.post("/create", response_model=CreateGameResponse)
async def create_game(request: Request):
    """
    Create a new game.

    Returns a new game with a unique 6-digit code.
    """
    game_manager = request.app.state.game_manager

    try:
        game = await game_manager.create_game()
        return CreateGameResponse(
            game_id=game.game_id,
            code=game.game_code,
            status=game.status,
        )
    except Exception as e:
        logger.error(f"Error creating game: {e}")
        raise HTTPException(status_code=500, detail="Failed to create game")


@router.post("/join/{code}", response_model=JoinGameResponse)
async def join_game(code: str, body: JoinGameRequest, request: Request):
    """
    Join an existing game by code.

    The first player to join becomes the host.
    """
    game_manager = request.app.state.game_manager

    try:
        # Validate and join game
        game, player_data = await game_manager.join_game(
            game_code=code,
            player_name=body.player_name,
            websocket_id=None,  # Will be set when WebSocket connects
            preferences=body.preferences,
        )

        # Broadcast updated player list to all clients in the room
        connection_manager = request.app.state.connection_manager
        await connection_manager.broadcast_to_room(
            game.game_id,
            "com.sc2ctl.jeopardy.player_list",
            {"players": game.state.get_players_dict()}
        )

        # Also broadcast game_ready if enough players have joined
        if game.can_start():
            await connection_manager.broadcast_to_room(
                game.game_id,
                "com.sc2ctl.jeopardy.game_ready",
                {"ready": True}
            )

        return JoinGameResponse(
            game_id=game.game_id,
            code=game.game_code,
            player_id=player_data["id"],
            player_name=player_data["name"],
            is_host=game.host_player_id == player_data["id"],
            status=game.status,
            players=[
                {"name": c.name, "score": c.score}
                for c in game.state.contestants.values()
            ],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error joining game: {e}")
        raise HTTPException(status_code=500, detail="Failed to join game")


@router.get("/{game_id}", response_model=GameStateResponse)
async def get_game(game_id: str, request: Request):
    """
    Get the current state of a game.
    """
    game_manager = request.app.state.game_manager

    game = await game_manager.get_game_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    lobby_state = game.get_lobby_state()
    return GameStateResponse(
        game_id=lobby_state["game_id"],
        code=lobby_state["game_code"],
        status=lobby_state["status"],
        players=lobby_state["players"],
        player_count=lobby_state["player_count"],
        can_start=lobby_state["can_start"],
        host_player_id=lobby_state["host_player_id"],
    )


@router.get("/code/{code}", response_model=GameStateResponse)
async def get_game_by_code(code: str, request: Request):
    """
    Get the current state of a game by its code.
    """
    game_manager = request.app.state.game_manager

    game = await game_manager.get_game_by_code(code)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    lobby_state = game.get_lobby_state()
    return GameStateResponse(
        game_id=lobby_state["game_id"],
        code=lobby_state["game_code"],
        status=lobby_state["status"],
        players=lobby_state["players"],
        player_count=lobby_state["player_count"],
        can_start=lobby_state["can_start"],
        host_player_id=lobby_state["host_player_id"],
    )


@router.post("/{game_id}/start")
async def start_game(game_id: str, body: StartGameRequest, request: Request):
    """
    Start a game (transition from lobby to active).

    Only the host can start the game.
    """
    game_manager = request.app.state.game_manager
    game_service = request.app.state.game_service

    game = await game_manager.get_game_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Check if requester is the host
    if game.host_player_id != body.player_id:
        raise HTTPException(status_code=403, detail="Only the host can start the game")

    # Check if enough players
    if not game.can_start():
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {game.REQUIRED_PLAYERS} players to start",
        )

    # Start the game
    success = await game_manager.start_game(game_id, game_service)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to start game")

    return {"status": "started", "game_id": game_id}


@router.delete("/{game_id}")
async def delete_game(game_id: str, request: Request):
    """
    Delete a game completely.

    This removes the game from memory.
    """
    game_manager = request.app.state.game_manager

    game = await game_manager.get_game_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    await game_manager.delete_game(game_id)
    return {"status": "deleted", "game_id": game_id}


@router.get("/")
async def list_games(request: Request):
    """
    List all active games (admin/debug endpoint).
    """
    game_manager = request.app.state.game_manager

    return {
        "games": game_manager.list_games(),
        "count": game_manager.get_active_game_count(),
    }
