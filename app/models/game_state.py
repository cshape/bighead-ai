from typing import Dict, Optional, List, Set
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class PlayerRegistry:
    """
    Per-game state manager. No longer a singleton - each game instance
    should create its own GameStateManager.
    """

    def __init__(self, game_id: Optional[str] = None, game_code: Optional[str] = None):
        """
        Initialize a new game state manager.

        Args:
            game_id: The unique game UUID (from database)
            game_code: The 6-digit game code for joining
        """
        self.game_id = game_id
        self.game_code = game_code
        self.contestants: Dict[str, 'Contestant'] = {}  # websocket_id -> Contestant
        self.current_question = None
        self.buzzer_active = False
        self.last_buzzer = None
        self.used_questions: Set[str] = set()  # Track used questions as "category:value"

    def register_contestant(self, websocket_id: str, name: str) -> bool:
        """Register a new contestant if name is available"""
        if any(c.name == name for c in self.contestants.values()):
            return False

        from ..models.contestant import Contestant
        self.contestants[websocket_id] = Contestant(name=name, score=0)
        logger.info(f"Registered contestant '{name}' with key '{websocket_id}' (game: {self.game_code})")
        logger.debug(f"Current contestants keys: {list(self.contestants.keys())}")
        return True

    def get_contestant_by_websocket(self, websocket_id: str) -> Optional['Contestant']:
        contestant = self.contestants.get(websocket_id)
        if not contestant:
            logger.warning(f"Lookup failed for key '{websocket_id}' (game: {self.game_code})")
            logger.warning(f"Available keys: {list(self.contestants.keys())}")
        return contestant

    def update_contestant_key(self, name: str, new_websocket_id: str) -> bool:
        """Update a contestant's key (for reconnection handling)"""
        # Find the contestant by name and get their current key
        old_key = None
        contestant = None
        for key, c in self.contestants.items():
            if c.name == name:
                old_key = key
                contestant = c
                break

        if not contestant:
            return False

        if old_key == new_websocket_id:
            # Already using the correct key
            return True

        # Re-key the contestant
        del self.contestants[old_key]
        self.contestants[new_websocket_id] = contestant
        logger.debug(f"Updated contestant '{name}' key from '{old_key}' to '{new_websocket_id}' (game: {self.game_code})")
        return True

    def get_contestant_by_name(self, name: str) -> Optional['Contestant']:
        """Get a contestant by their name"""
        for contestant in self.contestants.values():
            if contestant.name == name:
                return contestant
        return None

    def remove_contestant(self, websocket_id: str):
        if websocket_id in self.contestants:
            del self.contestants[websocket_id]

    def mark_question_used(self, category: str, value: int):
        """Mark a question as used"""
        self.used_questions.add(f"{category}:{value}")

    def is_question_used(self, category: str, value: int) -> bool:
        """Check if a question has been used"""
        return f"{category}:{value}" in self.used_questions

    def get_game_state(self) -> dict:
        """Get current game state for new connections"""
        return {
            "game_id": self.game_id,
            "game_code": self.game_code,
            "contestants": {
                ws_id: {"name": contestant.name, "score": contestant.score}
                for ws_id, contestant in self.contestants.items()
            },
            "current_question": self.current_question,
            "buzzer_active": self.buzzer_active,
            "last_buzzer": self.last_buzzer,
            "used_questions": list(self.used_questions)
        }

    def get_players_dict(self) -> Dict[str, dict]:
        """Get players as name -> info dict for frontend"""
        return {
            contestant.name: {"score": contestant.score}
            for contestant in self.contestants.values()
        }

    def reset(self):
        """Reset the game state for a new game"""
        self.contestants.clear()
        self.current_question = None
        self.buzzer_active = False
        self.last_buzzer = None
        self.used_questions.clear() 