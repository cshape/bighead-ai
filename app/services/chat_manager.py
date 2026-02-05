import logging
from typing import Dict, List, Optional
from ..websockets.connection_manager import ConnectionManager
from datetime import datetime

logger = logging.getLogger(__name__)


class ChatManager:
    """
    ChatManager handles the chat functionality for the game.
    It stores chat messages and broadcasts them to all connected clients.
    Supports multi-game with per-game chat history.
    """

    # Chat topic constant - should match the JavaScript client
    CHAT_MESSAGE_TOPIC = "com.sc2ctl.jeopardy.chat_message"

    def __init__(self, connection_manager: ConnectionManager):
        """
        Initialize the ChatManager with a connection to the websocket manager.

        Args:
            connection_manager: The websocket connection manager for sending messages
        """
        self.connection_manager = connection_manager
        self.chat_history: List[Dict] = []  # Legacy single-game chat history
        self.game_chat_history: Dict[str, List[Dict]] = {}  # game_id -> chat history
        self.max_history_size = 100  # Maximum number of chat messages to store

    async def handle_message(
        self, username: str, message: str, is_admin: bool = False, game_id: Optional[str] = None
    ):
        """
        Process and broadcast a chat message to all clients.

        Args:
            username: The name of the user sending the message
            message: The content of the chat message
            is_admin: Whether the message is from an admin (optional)
            game_id: Optional game ID for multi-game support
        """
        # Create the chat message object
        chat_message = {
            "username": username,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "is_admin": is_admin,
        }

        # Add to appropriate history
        if game_id:
            if game_id not in self.game_chat_history:
                self.game_chat_history[game_id] = []
            self.game_chat_history[game_id].append(chat_message)
            if len(self.game_chat_history[game_id]) > self.max_history_size:
                self.game_chat_history[game_id] = self.game_chat_history[game_id][
                    -self.max_history_size :
                ]
        else:
            # Legacy single-game mode
            self.chat_history.append(chat_message)
            if len(self.chat_history) > self.max_history_size:
                self.chat_history = self.chat_history[-self.max_history_size :]

        logger.debug(f"Chat message from {username}: {message}")

        # Broadcast to appropriate clients
        await self.connection_manager.broadcast_message(
            self.CHAT_MESSAGE_TOPIC, chat_message, game_id=game_id
        )

    async def send_chat_history(self, websocket, game_id: Optional[str] = None):
        """
        Send chat history to a newly connected client.

        Args:
            websocket: The websocket connection of the client
            game_id: Optional game ID for multi-game support
        """
        # Get appropriate history
        if game_id:
            history = self.game_chat_history.get(game_id, [])
        else:
            history = self.chat_history

        if not history:
            return

        await self.connection_manager.send_personal_message(
            websocket, "com.sc2ctl.jeopardy.chat_history", {"messages": history}
        )

    def clear_game_history(self, game_id: str):
        """Clear chat history for a specific game."""
        if game_id in self.game_chat_history:
            del self.game_chat_history[game_id] 