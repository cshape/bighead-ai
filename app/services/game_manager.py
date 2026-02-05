"""
GameManager - Central manager for multiple concurrent game instances.

Handles game creation, lookup, and lifecycle management.
"""

import asyncio
import logging
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta

from .game_instance import GameInstance
from ..database.repositories import GameRepository, PlayerRepository

logger = logging.getLogger(__name__)


class GameManager:
    """
    Central manager for all active game instances.

    Responsibilities:
    - Create new games
    - Look up games by code or ID
    - Manage game lifecycle
    - Clean up stale games
    """

    # Time after which inactive lobby games are cleaned up
    LOBBY_TIMEOUT_HOURS = 24
    # Time after which completed games are cleaned up
    COMPLETED_TIMEOUT_HOURS = 1

    def __init__(self):
        """Initialize the game manager."""
        self.active_games: Dict[str, GameInstance] = {}  # game_id -> GameInstance
        self.code_to_id: Dict[str, str] = {}  # game_code -> game_id
        self.game_repo = GameRepository()
        self.player_repo = PlayerRepository()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the game manager background tasks."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("GameManager started")

    async def stop(self):
        """Stop the game manager and clean up."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Stop all AI hosts
        for game in self.active_games.values():
            await game.stop_ai_host()

        logger.info("GameManager stopped")

    async def create_game(self) -> GameInstance:
        """
        Create a new game.

        Returns:
            The newly created GameInstance
        """
        # Create in database
        game_data = await self.game_repo.create_game()
        game_id = game_data["id"]
        game_code = game_data["code"]

        # Create in-memory instance
        game = GameInstance(game_id=game_id, game_code=game_code)

        # Store references
        self.active_games[game_id] = game
        self.code_to_id[game_code] = game_id

        logger.info(f"Created new game: {game_code} (ID: {game_id})")
        return game

    async def get_game_by_code(self, code: str) -> Optional[GameInstance]:
        """
        Get a game by its 6-digit code.

        Args:
            code: The game code (case-insensitive)

        Returns:
            GameInstance or None if not found
        """
        code = code.upper()

        # Check in-memory first
        game_id = self.code_to_id.get(code)
        if game_id:
            return self.active_games.get(game_id)

        # Check database and load if found
        game_data = await self.game_repo.get_game_by_code(code)
        if game_data:
            return await self._load_game_from_db(game_data)

        return None

    async def get_game_by_id(self, game_id: str) -> Optional[GameInstance]:
        """
        Get a game by its UUID.

        Args:
            game_id: The game UUID

        Returns:
            GameInstance or None if not found
        """
        # Check in-memory first
        if game_id in self.active_games:
            return self.active_games[game_id]

        # Check database and load if found
        game_data = await self.game_repo.get_game_by_id(game_id)
        if game_data:
            return await self._load_game_from_db(game_data)

        return None

    async def _load_game_from_db(self, game_data: Dict[str, Any]) -> GameInstance:
        """
        Load a game from database data into memory.

        Args:
            game_data: The game record from database

        Returns:
            The loaded GameInstance
        """
        game_id = game_data["id"]
        game_code = game_data["code"]

        # Check if already loaded
        if game_id in self.active_games:
            return self.active_games[game_id]

        # Create instance
        game = GameInstance(
            game_id=game_id,
            game_code=game_code,
            host_player_id=game_data.get("host_player_id"),
        )
        game.status = game_data.get("status", GameInstance.STATUS_LOBBY)
        game.board = game_data.get("board_data")
        game.current_question = game_data.get("current_question")
        game.buzzer_active = game_data.get("buzzer_active", False)

        # Load players
        players = await self.player_repo.get_players_in_game(game_id)
        for player in players:
            # Register player in state (using player ID as pseudo-websocket-id for now)
            game.state.register_contestant(player["id"], player["name"])
            contestant = game.state.get_contestant_by_websocket(player["id"])
            if contestant:
                contestant.score = player["score"]

        # Store references
        self.active_games[game_id] = game
        self.code_to_id[game_code] = game_id

        logger.info(f"Loaded game from database: {game_code} (ID: {game_id})")
        return game

    async def join_game(
        self,
        game_code: str,
        player_name: str,
        websocket_id: str,
        preferences: Optional[str] = None,
    ) -> tuple[GameInstance, Dict[str, Any]]:
        """
        Join an existing game.

        Args:
            game_code: The game code to join
            player_name: The player's name
            websocket_id: The WebSocket connection ID
            preferences: Optional player preferences

        Returns:
            Tuple of (GameInstance, player_data)

        Raises:
            ValueError: If game not found or player name taken
        """
        game = await self.get_game_by_code(game_code)
        if not game:
            raise ValueError(f"Game with code {game_code} not found")

        if game.status == GameInstance.STATUS_COMPLETED:
            raise ValueError("This game has already ended")

        # Check if name is taken
        if game.state.get_contestant_by_name(player_name):
            raise ValueError(f"Player name '{player_name}' is already taken")

        # Create player in database
        player_data = await self.player_repo.create_player(
            game_id=game.game_id,
            name=player_name,
            preferences=preferences,
            websocket_id=websocket_id,
        )

        # Register in game state (using player ID as key, not websocket_id which may be None)
        game.state.register_contestant(player_data["id"], player_name)
        game.add_client(websocket_id)

        # If this is the first player, make them the host
        if game.host_player_id is None:
            game.host_player_id = player_data["id"]
            await self.game_repo.set_host_player(game.game_id, player_data["id"])

        logger.info(f"Player {player_name} joined game {game_code}")
        return game, player_data

    async def start_game(self, game_id: str, game_service) -> bool:
        """
        Start a game (transition from lobby to active).

        Args:
            game_id: The game UUID
            game_service: The game service for AI host callbacks

        Returns:
            True if started successfully
        """
        game = await self.get_game_by_id(game_id)
        if not game:
            return False

        if game.status != GameInstance.STATUS_LOBBY:
            logger.warning(f"Cannot start game {game.game_code} - not in lobby state")
            return False

        if not game.can_start():
            logger.warning(
                f"Cannot start game {game.game_code} - need {game.REQUIRED_PLAYERS} players"
            )
            return False

        # Update status
        game.start_game()
        await self.game_repo.update_game_status(game_id, GameInstance.STATUS_ACTIVE)

        # Start AI host
        await game.start_ai_host(game_service)

        return True

    async def end_game(self, game_id: str):
        """
        End a game (transition to completed).

        Args:
            game_id: The game UUID
        """
        game = await self.get_game_by_id(game_id)
        if not game:
            return

        game.complete_game()
        await self.game_repo.update_game_status(game_id, GameInstance.STATUS_COMPLETED)
        await game.stop_ai_host()

    async def remove_game(self, game_id: str):
        """
        Remove a game from memory (database record persists).

        Args:
            game_id: The game UUID
        """
        if game_id in self.active_games:
            game = self.active_games[game_id]
            await game.stop_ai_host()

            # Remove from mappings
            self.code_to_id.pop(game.game_code, None)
            del self.active_games[game_id]

            logger.info(f"Removed game {game.game_code} from memory")

    async def delete_game(self, game_id: str):
        """
        Completely delete a game (memory and database).

        Args:
            game_id: The game UUID
        """
        await self.remove_game(game_id)
        await self.game_repo.delete_game(game_id)
        logger.info(f"Deleted game {game_id} from database")

    def get_game_for_client(self, client_id: str) -> Optional[GameInstance]:
        """
        Find which game a client is connected to.

        Args:
            client_id: The WebSocket client ID

        Returns:
            GameInstance or None if client not in any game
        """
        for game in self.active_games.values():
            if game.is_client_connected(client_id):
                return game
        return None

    async def _cleanup_loop(self):
        """Background task to clean up stale games."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                await self._cleanup_stale_games()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _cleanup_stale_games(self):
        """Remove stale games from memory."""
        now = datetime.utcnow()
        to_remove = []

        for game_id, game in self.active_games.items():
            age = now - game.created_at

            # Clean up old lobby games
            if game.status == GameInstance.STATUS_LOBBY:
                if age > timedelta(hours=self.LOBBY_TIMEOUT_HOURS):
                    to_remove.append(game_id)

            # Clean up old completed games
            elif game.status == GameInstance.STATUS_COMPLETED:
                if age > timedelta(hours=self.COMPLETED_TIMEOUT_HOURS):
                    to_remove.append(game_id)

        for game_id in to_remove:
            await self.remove_game(game_id)
            logger.info(f"Cleaned up stale game {game_id}")

    def get_active_game_count(self) -> int:
        """Get the count of active games in memory."""
        return len(self.active_games)

    def list_games(self) -> List[Dict[str, Any]]:
        """List all active games."""
        return [game.to_dict() for game in self.active_games.values()]
