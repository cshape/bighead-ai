"""
Game repository for Supabase database operations.
"""

import random
import string
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from ..client import get_supabase_client

logger = logging.getLogger(__name__)


class GameRepository:
    """Repository for game-related database operations."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_supabase_client()
        return self._client

    @staticmethod
    def generate_game_code() -> str:
        """Generate a unique 6-digit alphanumeric game code."""
        # Use uppercase letters and digits, excluding confusing characters
        chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(random.choices(chars, k=6))

    async def create_game(self, host_player_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new game with a unique code.

        Args:
            host_player_id: Optional UUID of the host player

        Returns:
            Dict containing game id and code
        """
        # Generate a unique code (retry if collision)
        max_attempts = 10
        for _ in range(max_attempts):
            code = self.generate_game_code()

            try:
                result = (
                    self.client.table("games")
                    .insert(
                        {
                            "code": code,
                            "status": "lobby",
                            "host_player_id": host_player_id,
                        }
                    )
                    .execute()
                )

                if result.data:
                    game = result.data[0]
                    logger.info(f"Created game with code {code}")
                    return {
                        "id": game["id"],
                        "code": game["code"],
                        "status": game["status"],
                        "created_at": game["created_at"],
                    }
            except Exception as e:
                # Code collision, try again
                if "duplicate key" in str(e).lower():
                    continue
                raise

        raise Exception("Failed to generate unique game code after multiple attempts")

    async def get_game_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Get a game by its 6-digit code.

        Args:
            code: The game code (case-insensitive)

        Returns:
            Game data dict or None if not found
        """
        result = (
            self.client.table("games")
            .select("*")
            .eq("code", code.upper())
            .execute()
        )

        if result.data:
            return result.data[0]
        return None

    async def get_game_by_id(self, game_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a game by its UUID.

        Args:
            game_id: The game UUID

        Returns:
            Game data dict or None if not found
        """
        result = self.client.table("games").select("*").eq("id", game_id).execute()

        if result.data:
            return result.data[0]
        return None

    async def update_game_status(self, game_id: str, status: str) -> bool:
        """
        Update the game status.

        Args:
            game_id: The game UUID
            status: New status ('lobby', 'active', 'completed')

        Returns:
            True if updated successfully
        """
        result = (
            self.client.table("games")
            .update({"status": status, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", game_id)
            .execute()
        )

        return len(result.data) > 0

    async def update_game_board(self, game_id: str, board_data: Dict[str, Any]) -> bool:
        """
        Update the game's board data.

        Args:
            game_id: The game UUID
            board_data: The board data as JSON

        Returns:
            True if updated successfully
        """
        result = (
            self.client.table("games")
            .update(
                {"board_data": board_data, "updated_at": datetime.utcnow().isoformat()}
            )
            .eq("id", game_id)
            .execute()
        )

        return len(result.data) > 0

    async def update_current_question(
        self, game_id: str, question_data: Optional[Dict[str, Any]]
    ) -> bool:
        """
        Update the current question being displayed.

        Args:
            game_id: The game UUID
            question_data: The question data or None to clear

        Returns:
            True if updated successfully
        """
        result = (
            self.client.table("games")
            .update(
                {
                    "current_question": question_data,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )
            .eq("id", game_id)
            .execute()
        )

        return len(result.data) > 0

    async def update_buzzer_status(self, game_id: str, active: bool) -> bool:
        """
        Update the buzzer active status.

        Args:
            game_id: The game UUID
            active: Whether the buzzer is active

        Returns:
            True if updated successfully
        """
        result = (
            self.client.table("games")
            .update(
                {"buzzer_active": active, "updated_at": datetime.utcnow().isoformat()}
            )
            .eq("id", game_id)
            .execute()
        )

        return len(result.data) > 0

    async def set_host_player(self, game_id: str, player_id: str) -> bool:
        """
        Set the host player for a game.

        Args:
            game_id: The game UUID
            player_id: The player UUID to set as host

        Returns:
            True if updated successfully
        """
        result = (
            self.client.table("games")
            .update(
                {
                    "host_player_id": player_id,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )
            .eq("id", game_id)
            .execute()
        )

        return len(result.data) > 0

    async def delete_game(self, game_id: str) -> bool:
        """
        Delete a game (cascades to players, used_questions, chat_messages).

        Args:
            game_id: The game UUID

        Returns:
            True if deleted successfully
        """
        result = self.client.table("games").delete().eq("id", game_id).execute()

        return len(result.data) > 0

    async def mark_question_used(
        self,
        game_id: str,
        category_name: str,
        question_value: int,
        answered_by: Optional[str] = None,
        answered_correctly: Optional[bool] = None,
    ) -> bool:
        """
        Mark a question as used in a game.

        Args:
            game_id: The game UUID
            category_name: The category name
            question_value: The question value
            answered_by: Optional name of player who answered
            answered_correctly: Optional whether they answered correctly

        Returns:
            True if recorded successfully
        """
        try:
            result = (
                self.client.table("used_questions")
                .insert(
                    {
                        "game_id": game_id,
                        "category_name": category_name,
                        "question_value": question_value,
                        "answered_by": answered_by,
                        "answered_correctly": answered_correctly,
                    }
                )
                .execute()
            )
            return len(result.data) > 0
        except Exception as e:
            # Already used (unique constraint)
            logger.warning(f"Question already marked as used: {e}")
            return False

    async def get_used_questions(self, game_id: str) -> List[Dict[str, Any]]:
        """
        Get all used questions for a game.

        Args:
            game_id: The game UUID

        Returns:
            List of used question records
        """
        result = (
            self.client.table("used_questions")
            .select("*")
            .eq("game_id", game_id)
            .execute()
        )

        return result.data or []

    async def add_chat_message(
        self, game_id: str, username: str, message: str, is_admin: bool = False
    ) -> Dict[str, Any]:
        """
        Add a chat message to a game.

        Args:
            game_id: The game UUID
            username: The username of the sender
            message: The message text
            is_admin: Whether this is an admin message

        Returns:
            The created message record
        """
        result = (
            self.client.table("chat_messages")
            .insert(
                {
                    "game_id": game_id,
                    "username": username,
                    "message": message,
                    "is_admin": is_admin,
                }
            )
            .execute()
        )

        if result.data:
            return result.data[0]
        raise Exception("Failed to create chat message")

    async def get_chat_messages(
        self, game_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get chat messages for a game.

        Args:
            game_id: The game UUID
            limit: Maximum number of messages to return

        Returns:
            List of chat message records, ordered by creation time
        """
        result = (
            self.client.table("chat_messages")
            .select("*")
            .eq("game_id", game_id)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )

        return result.data or []
