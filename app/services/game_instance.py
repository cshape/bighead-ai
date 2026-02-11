"""
GameInstance - Per-game state container for multi-game support.

Each game instance holds its own state, AI host, and manages its own
set of connected players.
"""

import asyncio
import logging
from typing import Dict, Optional, Any, List, Set
from datetime import datetime

from ..models.game_state import PlayerRegistry
from ..models.board import Board
from ..ai.host import AIHostService
from ..ai.llm_state_manager import LLMStateManager

logger = logging.getLogger(__name__)


class GameInstance:
    """
    Container for a single game's state and services.

    Each game instance has:
    - Its own GameStateManager
    - Its own AI Host (optional)
    - Its own board state
    - Set of connected WebSocket client IDs
    """

    # Game status constants
    STATUS_LOBBY = "lobby"
    STATUS_ACTIVE = "active"
    STATUS_COMPLETED = "completed"

    # Required players to start (can be overridden)
    REQUIRED_PLAYERS = 1

    DEFAULT_VOICE = "Clive"

    def __init__(
        self,
        game_id: str,
        game_code: str,
        host_player_id: Optional[str] = None,
        voice: Optional[str] = None,
    ):
        """
        Initialize a new game instance.

        Args:
            game_id: The unique game UUID
            game_code: The 6-digit game code
            host_player_id: Optional player UUID who is the host
            voice: Optional TTS voice ID for the AI host
        """
        self.game_id = game_id
        self.game_code = game_code
        self.host_player_id = host_player_id
        self.voice = voice or self.DEFAULT_VOICE
        self.status = self.STATUS_LOBBY
        self.created_at = datetime.utcnow()

        # Game state
        self.state = PlayerRegistry(game_id=game_id, game_code=game_code)
        self.llm_state = LLMStateManager(game_id=game_id)
        self.board: Optional[Dict[str, Any]] = None
        self.current_question = None
        self._buzzer_active = False
        self._last_buzzer = None
        self.game_ready = False
        self.completed_audio_ids: Set[str] = set()
        self.audio_events: Dict[str, asyncio.Event] = {}  # For event-based completion signaling

        # Connected clients for this game (websocket_id -> websocket)
        self.connected_clients: Set[str] = set()

        # Restart support
        self.is_restart = False
        self.stored_preferences: Optional[Dict[str, str]] = None

        # AI Host (created on demand)
        self._ai_host: Optional[AIHostService] = None
        self._ai_host_task: Optional[asyncio.Task] = None

    @property
    def ai_host(self) -> AIHostService:
        """Get or create the AI host service for this game."""
        if self._ai_host is None:
            self._ai_host = AIHostService(
                name=f"AI Host ({self.game_code})",
                voice=self.voice,
            )
        return self._ai_host

    @property
    def buzzer_active(self) -> bool:
        """Delegate buzzer_active to BuzzerManager when AI host is initialized."""
        if self._ai_host is not None:
            return self._ai_host.buzzer_manager.buzzer_active
        return self._buzzer_active

    @buzzer_active.setter
    def buzzer_active(self, value: bool):
        if self._ai_host is not None:
            self._ai_host.buzzer_manager.buzzer_active = value
        self._buzzer_active = value

    @property
    def last_buzzer(self):
        """Delegate last_buzzer to BuzzerManager when AI host is initialized."""
        if self._ai_host is not None:
            return self._ai_host.buzzer_manager.last_buzzer
        return self._last_buzzer

    @last_buzzer.setter
    def last_buzzer(self, value):
        if self._ai_host is not None:
            self._ai_host.buzzer_manager.last_buzzer = value
        self._last_buzzer = value

    @property
    def player_count(self) -> int:
        """Get the number of registered players."""
        return len(self.state.contestants)

    def add_client(self, client_id: str):
        """Add a connected client to this game."""
        self.connected_clients.add(client_id)
        logger.debug(f"Client {client_id} joined game {self.game_code}")

    def remove_client(self, client_id: str):
        """Remove a connected client from this game.

        Note: Does NOT remove the contestant from the game state.
        Players register via HTTP and their registration persists
        independently of WebSocket connection state.
        """
        self.connected_clients.discard(client_id)
        logger.debug(f"Client {client_id} left game {self.game_code}")

    def is_client_connected(self, client_id: str) -> bool:
        """Check if a client is connected to this game."""
        return client_id in self.connected_clients

    def can_start(self) -> bool:
        """Check if the game has enough players to start."""
        return self.player_count >= self.REQUIRED_PLAYERS

    def is_host(self, player_id: str) -> bool:
        """Check if a player is the host."""
        return self.host_player_id == player_id

    def start_game(self):
        """Mark the game as active/started."""
        self.status = self.STATUS_ACTIVE
        self.game_ready = True
        logger.info(f"Game {self.game_code} started")

    def complete_game(self):
        """Mark the game as completed."""
        self.status = self.STATUS_COMPLETED
        logger.info(f"Game {self.game_code} completed")

    def restart_game(self):
        """Reset game state for a new round, preserving players and preferences."""
        self.board = None
        self.current_question = None
        self.status = self.STATUS_ACTIVE
        self.game_ready = True
        self.is_restart = True

        # Reset scores
        for contestant in self.state.contestants.values():
            contestant.score = 0

        # Clear used questions tracking
        if hasattr(self.state, 'used_questions'):
            self.state.used_questions.clear()

        logger.info(f"Game {self.game_code} restarted")

    async def start_ai_host(self, game_service):
        """
        Start the AI host for this game.

        Args:
            game_service: The game service reference for callbacks
        """
        if self._ai_host_task is not None:
            logger.warning(f"AI host already running for game {self.game_code}")
            return

        # Set up dependencies - pass both game_service and this game_instance
        self.ai_host.set_game_service(game_service, game_instance=self)

        # Start the AI host task
        self._ai_host_task = asyncio.create_task(self.ai_host.run())
        logger.info(f"AI host started for game {self.game_code}")

    async def stop_ai_host(self):
        """Stop the AI host for this game."""
        if self._ai_host_task is not None:
            self._ai_host_task.cancel()
            try:
                await self._ai_host_task
            except asyncio.CancelledError:
                pass
            self._ai_host_task = None
            logger.info(f"AI host stopped for game {self.game_code}")

    def mark_audio_completed(self, audio_id: str):
        """Mark an audio playback as completed and signal any waiting tasks."""
        self.completed_audio_ids.add(audio_id)
        # Signal the event if anyone is waiting
        if audio_id in self.audio_events:
            self.audio_events[audio_id].set()

    def is_audio_completed(self, audio_id: str) -> bool:
        """Check if an audio has been completed."""
        return audio_id in self.completed_audio_ids

    def check_audio_completed(self, audio_id: str) -> bool:
        """Check if an audio has been completed (alias for is_audio_completed)."""
        return self.is_audio_completed(audio_id)

    async def wait_for_audio_completion(self, audio_id: str, timeout: float = 30.0) -> bool:
        """Wait for audio completion using asyncio.Event instead of polling.

        Returns True if completed, False if timed out.
        """
        # Check if already completed
        if audio_id in self.completed_audio_ids:
            return True

        # Create event if not exists
        if audio_id not in self.audio_events:
            self.audio_events[audio_id] = asyncio.Event()

        try:
            await asyncio.wait_for(
                self.audio_events[audio_id].wait(),
                timeout=timeout
            )
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            # Cleanup event
            self.audio_events.pop(audio_id, None)

    def get_state_for_client(self) -> Dict[str, Any]:
        """Get the game state to send to a new client."""
        controlling_player = None
        if self._ai_host and self._ai_host.game_state_manager:
            controlling_player = self._ai_host.game_state_manager.get_player_with_control()
        return {
            "game_id": self.game_id,
            "game_code": self.game_code,
            "status": self.status,
            "players": self.state.get_players_dict(),
            "board": self.board,
            "current_question": self.current_question,
            "buzzer_active": self.buzzer_active,
            "last_buzzer": self.last_buzzer,
            "game_ready": self.game_ready,
            "is_host": False,  # Will be set by caller based on client
            "controlling_player": controlling_player,
        }

    def get_lobby_state(self) -> Dict[str, Any]:
        """Get the lobby state for waiting room display."""
        return {
            "game_id": self.game_id,
            "game_code": self.game_code,
            "status": self.status,
            "players": [
                {"name": c.name, "score": c.score}
                for c in self.state.contestants.values()
            ],
            "player_count": self.player_count,
            "required_players": self.REQUIRED_PLAYERS,
            "can_start": self.can_start(),
            "host_player_id": self.host_player_id,
            "voice": self.voice,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "game_id": self.game_id,
            "game_code": self.game_code,
            "status": self.status,
            "player_count": self.player_count,
            "created_at": self.created_at.isoformat(),
        }
