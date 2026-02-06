"""
WebSocket message router with Pydantic validation.

Routes incoming messages to typed handler functions based on topic.
"""

import logging
from typing import Dict, Tuple, Type, Callable, Any
from pydantic import BaseModel, ValidationError
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class MessageRouter:
    """Registry that maps message topics to (model, handler) pairs."""

    def __init__(self):
        self._routes: Dict[str, Tuple[Type[BaseModel], Callable]] = {}

    def route(self, topic: str, model: Type[BaseModel]):
        """Decorator to register a handler for a topic.

        Usage::

            @router.route("com.sc2ctl.jeopardy.buzzer", BuzzerMsg)
            async def handle_buzzer(ws, client_id, payload, game_id, game):
                ...
        """
        def decorator(fn: Callable) -> Callable:
            self._routes[topic] = (model, fn)
            return fn
        return decorator

    async def dispatch(
        self,
        websocket: WebSocket,
        client_id: str,
        data: dict,
        game_id: str,
        game: Any,
    ):
        """Validate and dispatch a message to the registered handler.

        Args:
            websocket: The sender's WebSocket connection.
            client_id: Unique client identifier.
            data: Raw message dict (must contain ``topic`` and optional ``payload``).
            game_id: The game this message belongs to.
            game: The ``GameInstance`` object (may be ``None`` if game not found).
        """
        topic = data.get("topic")
        payload = data.get("payload", {})

        if topic not in self._routes:
            logger.warning(f"Unknown topic: {topic}")
            return

        model_cls, handler = self._routes[topic]

        try:
            validated = model_cls(**payload)
        except ValidationError as exc:
            logger.warning(f"Validation error for topic {topic}: {exc}")
            from .connection_manager import ConnectionManager
            # Send structured error back to client
            try:
                await websocket.send_json({
                    "topic": "com.sc2ctl.jeopardy.error",
                    "payload": {
                        "message": f"Invalid payload for {topic}",
                        "details": exc.errors(),
                    },
                })
            except Exception:
                pass
            return

        await handler(websocket, client_id, validated, game_id, game)
