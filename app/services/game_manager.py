"""
GameManager - Central manager for multiple concurrent game instances.

Handles game creation, lookup, and lifecycle management.
All state is in-memory — games are ephemeral.
"""

import asyncio
import logging
import random
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
from uuid import uuid4

from .game_instance import GameInstance

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

    # Characters for game codes (excluding confusing ones like 0/O, 1/I/L)
    _CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    def __init__(self):
        """Initialize the game manager."""
        self.active_games: Dict[str, GameInstance] = {}  # game_id -> GameInstance
        self.code_to_id: Dict[str, str] = {}  # game_code -> game_id
        self._cleanup_task: Optional[asyncio.Task] = None

    def _generate_game_code(self) -> str:
        """Generate a unique 6-digit alphanumeric game code."""
        while True:
            code = "".join(random.choices(self._CODE_CHARS, k=6))
            if code not in self.code_to_id:
                return code

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
        game_id = str(uuid4())
        game_code = self._generate_game_code()

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
        game_id = self.code_to_id.get(code)
        if game_id:
            return self.active_games.get(game_id)
        return None

    async def get_game_by_id(self, game_id: str) -> Optional[GameInstance]:
        """
        Get a game by its UUID.

        Args:
            game_id: The game UUID

        Returns:
            GameInstance or None if not found
        """
        return self.active_games.get(game_id)

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

        # Generate player ID locally
        player_id = str(uuid4())
        player_data = {"id": player_id, "name": player_name}

        # Register in game state
        registration_key = websocket_id if websocket_id else player_id
        game.state.register_contestant(registration_key, player_name, player_id=player_id)
        if preferences and hasattr(game.ai_host, 'game_state_manager'):
            game.ai_host.game_state_manager.add_player_preference(player_name, preferences)
        if websocket_id:
            game.add_client(websocket_id)

        # If this is the first player, make them the host
        if game.host_player_id is None:
            game.host_player_id = player_id

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
        await game.stop_ai_host()

    async def remove_game(self, game_id: str):
        """
        Remove a game from memory.

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
        Completely delete a game.

        Args:
            game_id: The game UUID
        """
        await self.remove_game(game_id)
        logger.info(f"Deleted game {game_id}")

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
