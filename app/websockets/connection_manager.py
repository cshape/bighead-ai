import logging
import json
from typing import List, Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
import uuid

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    WebSocket connection manager with room-based isolation for multi-game support.

    Each game is treated as a "room" and messages can be broadcast to:
    - All clients (global)
    - All clients in a specific game room
    - A single client
    """

    def __init__(self):
        # All active connections: client_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

        # Room membership: game_id -> set of client_ids
        self.rooms: Dict[str, Set[str]] = {}

        # Reverse lookup: client_id -> game_id
        self.client_rooms: Dict[str, str] = {}

        # Legacy support
        self.admin_connections: List[WebSocket] = []
        self.player_connections: List[WebSocket] = []
        self.topic_subscriptions: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, game_id: Optional[str] = None) -> str:
        """
        Connect a websocket and optionally join a game room.

        Args:
            websocket: The WebSocket connection
            game_id: Optional game ID to join immediately

        Returns:
            The generated client_id
        """
        await websocket.accept()
        client_id = str(uuid.uuid4())
        self.active_connections[client_id] = websocket

        if game_id:
            self.join_room(client_id, game_id)

        logger.info(f"Client {client_id} connected" + (f" to game {game_id}" if game_id else ""))
        return client_id

    def join_room(self, client_id: str, game_id: str):
        """
        Add a client to a game room.

        Args:
            client_id: The client's connection ID
            game_id: The game ID to join
        """
        # Leave any existing room first
        if client_id in self.client_rooms:
            self.leave_room(client_id)

        # Join the new room
        if game_id not in self.rooms:
            self.rooms[game_id] = set()
        self.rooms[game_id].add(client_id)
        self.client_rooms[client_id] = game_id

        logger.debug(f"Client {client_id} joined room {game_id}")

    def leave_room(self, client_id: str):
        """
        Remove a client from their current game room.

        Args:
            client_id: The client's connection ID
        """
        if client_id in self.client_rooms:
            game_id = self.client_rooms[client_id]
            if game_id in self.rooms:
                self.rooms[game_id].discard(client_id)
                # Clean up empty rooms
                if not self.rooms[game_id]:
                    del self.rooms[game_id]
            del self.client_rooms[client_id]
            logger.debug(f"Client {client_id} left room {game_id}")

    def get_client_room(self, client_id: str) -> Optional[str]:
        """Get the game ID a client is connected to."""
        return self.client_rooms.get(client_id)

    def get_client_id_for_websocket(self, websocket: WebSocket) -> Optional[str]:
        """Get the client ID for a WebSocket connection."""
        for client_id, conn in self.active_connections.items():
            if conn == websocket:
                return client_id
        return None

    async def disconnect(self, websocket: WebSocket) -> Optional[str]:
        """
        Disconnect a websocket and remove from any rooms.

        Returns:
            The client_id that was disconnected, or None
        """
        to_remove = None
        for client_id, conn in self.active_connections.items():
            if conn == websocket:
                to_remove = client_id
                break

        if to_remove:
            self.leave_room(to_remove)
            del self.active_connections[to_remove]
            logger.info(f"Client {to_remove} disconnected")

        return to_remove

    async def send_personal_message(self, websocket: WebSocket, topic: str, payload: dict):
        """Send a message to a specific client by WebSocket."""
        message = {"topic": topic, "payload": payload}
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

    async def send_to_client(self, client_id: str, topic: str, payload: dict):
        """Send a message to a specific client by client_id."""
        if client_id in self.active_connections:
            message = {"topic": topic, "payload": payload}
            try:
                await self.active_connections[client_id].send_json(message)
            except Exception as e:
                logger.error(f"Error sending to client {client_id}: {e}")

    async def broadcast_to_room(self, game_id: str, topic: str, payload: dict):
        """
        Broadcast a message to all clients in a specific game room.

        Args:
            game_id: The game ID to broadcast to
            topic: The message topic
            payload: The message payload
        """
        if game_id not in self.rooms:
            logger.warning(f"No room found for game {game_id}")
            return

        message = {"topic": topic, "payload": payload}
        disconnected = []

        for client_id in self.rooms[game_id].copy():
            if client_id in self.active_connections:
                try:
                    await self.active_connections[client_id].send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to {client_id}: {e}")
                    disconnected.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected:
            if client_id in self.active_connections:
                websocket = self.active_connections[client_id]
                await self.disconnect(websocket)

    async def broadcast_message(self, topic: str, payload: dict, game_id: Optional[str] = None):
        """
        Broadcast a message to all clients, optionally filtered by game.

        For backward compatibility, if game_id is None, broadcasts to ALL clients.
        For multi-game support, provide game_id to scope the broadcast.

        Args:
            topic: The message topic
            payload: The message payload
            game_id: Optional game ID to scope the broadcast
        """
        if game_id:
            await self.broadcast_to_room(game_id, topic, payload)
            return

        # Legacy: broadcast to all (for backwards compatibility during migration)
        message = {"topic": topic, "payload": payload}
        disconnected = []

        for client_id, connection in self.active_connections.items():
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected:
            if client_id in self.active_connections:
                websocket = self.active_connections[client_id]
                await self.disconnect(websocket)

    def get_room_client_count(self, game_id: str) -> int:
        """Get the number of clients in a game room."""
        return len(self.rooms.get(game_id, set()))

    def get_room_clients(self, game_id: str) -> Set[str]:
        """Get all client IDs in a game room."""
        return self.rooms.get(game_id, set()).copy()

    async def broadcast_to_topic(self, topic: str, message: dict):
        if topic not in self.topic_subscriptions:
            return
            
        message_json = json.dumps(message)
        subscribers = self.topic_subscriptions[topic].copy()
        
        for websocket in subscribers:
            try:
                await websocket.send_text(message_json)
            except Exception as e:
                logger.error(f"Failed to send to subscriber {id(websocket)}: {e}")
                await self.disconnect(websocket)
    
    async def broadcast(self, data: dict):
        json_data = json.dumps(data)
        for connection in self.active_connections.values():
            try:
                await connection.send_text(json_data)
            except Exception:
                # Handle disconnections or errors
                await self.disconnect(connection)

    async def handle_message(self, websocket: WebSocket, message_data: str):
        """Handle incoming WebSocket message and route to appropriate handler"""
        try:
            message = json.loads(message_data)
            
            # Get the topic and payload from the message
            topic = message.get("topic")
            payload = message.get("payload", {})
            
            logging.info(f"Received message on topic: {topic}")
            
            # Handle based on topic
            if topic == "com.sc2ctl.jeopardy.buzzer":
                await self.handle_buzzer(websocket, payload)
            elif topic == "com.sc2ctl.jeopardy.chat":
                await self.handle_chat(websocket, payload)
            elif topic == "com.sc2ctl.jeopardy.register":
                await self.handle_registration(websocket, payload)
            elif topic == "com.sc2ctl.jeopardy.select_board":
                await self.handle_board_selection(websocket, payload)
            elif topic == "com.sc2ctl.jeopardy.select_question":
                await self.handle_question_selection(websocket, payload)
            elif topic == "com.sc2ctl.jeopardy.audio_complete":
                await self.handle_audio_complete(websocket, payload)
            else:
                logging.warning(f"Unhandled message topic: {topic}")
        except json.JSONDecodeError:
            logging.error(f"Invalid message format: {message_data}")
        except Exception as e:
            logging.error(f"Error handling message: {e}")
            
    async def handle_audio_complete(self, websocket: WebSocket, payload: Dict):
        """Handle audio completion notifications from clients.

        Note: Audio completion is now handled through the WebSocket handler in main.py
        which has proper game context. This method is kept for backwards compatibility
        but simply logs the event.
        """
        audio_id = payload.get("audio_id")
        if not audio_id:
            logging.warning("Audio completion message missing audio_id")
            return

        logging.info(f"🔊 WebSocket audio completion received: {audio_id} (handled by main.py)") 