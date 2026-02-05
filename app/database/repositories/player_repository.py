"""
Player repository for Supabase database operations.
"""

from typing import Optional, Dict, Any, List
import logging

from ..client import get_supabase_client

logger = logging.getLogger(__name__)


class PlayerRepository:
    """Repository for player-related database operations."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_supabase_client()
        return self._client

    async def create_player(
        self,
        game_id: str,
        name: str,
        preferences: Optional[str] = None,
        websocket_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new player in a game.

        Args:
            game_id: The game UUID
            name: The player's name
            preferences: Optional player preferences
            websocket_id: Optional WebSocket connection ID

        Returns:
            The created player record

        Raises:
            Exception: If player name already exists in game
        """
        try:
            result = (
                self.client.table("players")
                .insert(
                    {
                        "game_id": game_id,
                        "name": name,
                        "preferences": preferences,
                        "websocket_id": websocket_id,
                        "score": 0,
                    }
                )
                .execute()
            )

            if result.data:
                player = result.data[0]
                logger.info(f"Created player {name} in game {game_id}")
                return player

            raise Exception("Failed to create player")
        except Exception as e:
            if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
                raise Exception(f"Player name '{name}' already exists in this game")
            raise

    async def get_player_by_id(self, player_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a player by their UUID.

        Args:
            player_id: The player UUID

        Returns:
            Player data dict or None if not found
        """
        result = self.client.table("players").select("*").eq("id", player_id).execute()

        if result.data:
            return result.data[0]
        return None

    async def get_player_by_name(
        self, game_id: str, name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a player by their name within a game.

        Args:
            game_id: The game UUID
            name: The player's name

        Returns:
            Player data dict or None if not found
        """
        result = (
            self.client.table("players")
            .select("*")
            .eq("game_id", game_id)
            .eq("name", name)
            .execute()
        )

        if result.data:
            return result.data[0]
        return None

    async def get_player_by_websocket(
        self, game_id: str, websocket_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a player by their WebSocket connection ID.

        Args:
            game_id: The game UUID
            websocket_id: The WebSocket connection ID

        Returns:
            Player data dict or None if not found
        """
        result = (
            self.client.table("players")
            .select("*")
            .eq("game_id", game_id)
            .eq("websocket_id", websocket_id)
            .execute()
        )

        if result.data:
            return result.data[0]
        return None

    async def get_players_in_game(self, game_id: str) -> List[Dict[str, Any]]:
        """
        Get all players in a game.

        Args:
            game_id: The game UUID

        Returns:
            List of player records
        """
        result = (
            self.client.table("players")
            .select("*")
            .eq("game_id", game_id)
            .order("joined_at", desc=False)
            .execute()
        )

        return result.data or []

    async def update_player_score(self, player_id: str, score: int) -> bool:
        """
        Update a player's score.

        Args:
            player_id: The player UUID
            score: The new score

        Returns:
            True if updated successfully
        """
        result = (
            self.client.table("players")
            .update({"score": score})
            .eq("id", player_id)
            .execute()
        )

        return len(result.data) > 0

    async def update_player_websocket(
        self, player_id: str, websocket_id: Optional[str]
    ) -> bool:
        """
        Update a player's WebSocket connection ID.

        Args:
            player_id: The player UUID
            websocket_id: The new WebSocket ID or None to clear

        Returns:
            True if updated successfully
        """
        result = (
            self.client.table("players")
            .update({"websocket_id": websocket_id})
            .eq("id", player_id)
            .execute()
        )

        return len(result.data) > 0

    async def update_player_preferences(
        self, player_id: str, preferences: str
    ) -> bool:
        """
        Update a player's preferences.

        Args:
            player_id: The player UUID
            preferences: The preferences string

        Returns:
            True if updated successfully
        """
        result = (
            self.client.table("players")
            .update({"preferences": preferences})
            .eq("id", player_id)
            .execute()
        )

        return len(result.data) > 0

    async def delete_player(self, player_id: str) -> bool:
        """
        Delete a player.

        Args:
            player_id: The player UUID

        Returns:
            True if deleted successfully
        """
        result = self.client.table("players").delete().eq("id", player_id).execute()

        return len(result.data) > 0

    async def get_scores_for_game(self, game_id: str) -> Dict[str, int]:
        """
        Get all player scores for a game as a name -> score dict.

        Args:
            game_id: The game UUID

        Returns:
            Dict mapping player names to their scores
        """
        players = await self.get_players_in_game(game_id)
        return {player["name"]: player["score"] for player in players}
