from fastapi import WebSocket
import asyncio
import time
from ..websockets.connection_manager import ConnectionManager
import logging
from ..ai.host.buzzer_manager import BuzzerManager
import json
from pathlib import Path
import re

logger = logging.getLogger(__name__)

class GameService:
    # Constants for topic names - should match JavaScript client
    BUZZER_TOPIC = "com.sc2ctl.jeopardy.buzzer"
    BUZZER_STATUS_TOPIC = "com.sc2ctl.jeopardy.buzzer_status"
    QUESTION_DISPLAY_TOPIC = "com.sc2ctl.jeopardy.question_display"
    QUESTION_DISMISS_TOPIC = "com.sc2ctl.jeopardy.question_dismiss"
    QUESTION_ANSWER_TOPIC = "com.sc2ctl.jeopardy.answer"
    CONTESTANT_SCORE_TOPIC = "com.sc2ctl.jeopardy.contestant_score"
    DAILY_DOUBLE_BET_TOPIC = "com.sc2ctl.jeopardy.daily_double_bet"
    FINAL_JEOPARDY_TOPIC = "com.sc2ctl.jeopardy.final_jeopardy"
    FINAL_JEOPARDY_RESPONSES_TOPIC = "com.sc2ctl.jeopardy.final_jeopardy_responses"
    FINAL_JEOPARDY_ANSWER_TOPIC = "com.sc2ctl.jeopardy.final_jeopardy_answers"
    BOARD_INIT_TOPIC = "com.sc2ctl.jeopardy.board_init"
    AUDIO_PLAY_TOPIC = "com.sc2ctl.jeopardy.play_audio"
    AUDIO_COMPLETE_TOPIC = "com.sc2ctl.jeopardy.audio_complete"
    
    # Timeouts
    BUZZER_RESOLVE_TIMEOUT = 0.75  # seconds
    FINAL_JEOPARDY_COLLECTION_TIMEOUT = 5.5  # seconds
    
    REQUIRED_PLAYERS = 3
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self.boards_path = Path("app/game_data")

        # Reference to game manager (set in main.py)
        self.game_manager = None

    def set_game_manager(self, game_manager):
        """Set reference to game manager for multi-game lookups."""
        self.game_manager = game_manager

    async def _get_game(self, game_id: str):
        """Get game instance - required for all operations."""
        if not game_id:
            raise ValueError("game_id is required")
        if not self.game_manager:
            raise ValueError("game_manager not set")
        game = await self.game_manager.get_game_by_id(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")
        return game

    def _get_buzzer_manager(self, game) -> BuzzerManager:
        """Get the buzzer manager for the game."""
        return game.ai_host.buzzer_manager
    
    async def select_board(self, board_id: str, game_id: str):
        """Load and initialize a new board for a game"""
        try:
            game = await self._get_game(game_id)

            board_path = self.boards_path / f"{board_id}.json"
            if not board_path.exists():
                logger.error(f"Board file not found: {board_path}")
                raise FileNotFoundError(f"Board {board_id} not found")

            logger.info(f"Loading board from {board_path}")
            with open(board_path, 'r') as f:
                board_data = json.load(f)
                game.board = board_data
                logger.info(f"Successfully loaded board: {board_id}")

            # Send the board to appropriate clients
            await self.connection_manager.broadcast_message(
                "com.sc2ctl.jeopardy.board_selected",
                {"categories": board_data["categories"]},
                game_id=game_id
            )
        except Exception as e:
            logger.error(f"Error selecting board: {e}")
            await self.connection_manager.broadcast_message(
                "com.sc2ctl.jeopardy.error",
                {"message": f"Failed to load board: {str(e)}"},
                game_id=game_id
            )
    
    async def send_categories(self, game_id: str):
        """Send all categories and questions to clients"""
        game = await self._get_game(game_id)
        board = game.board

        if not board:
            return

        # Handle both dict and object formats
        if isinstance(board, dict):
            categories = board.get("categories", [])
        else:
            categories = [category.dict() for category in board.categories]

        await self.connection_manager.broadcast_message(
            self.BOARD_INIT_TOPIC,
            {"categories": categories},
            game_id=game_id
        )

        # Update LLM state with available categories
        if isinstance(board, dict):
            cat_names = [cat["name"] for cat in board.get("categories", [])]
        else:
            cat_names = [category.name for category in board.categories]
        game.llm_state.update_categories(cat_names)
    
    def _get_question_manager(self, game):
        """Get the question manager for the game."""
        return game.ai_host.question_manager

    async def display_question(self, category_name: str, value: int, game_id: str):
        """Delegate to QuestionManager."""
        game = await self._get_game(game_id)
        await self._get_question_manager(game).display_question(category_name, value, game_id)

    async def dismiss_question(self, game_id: str):
        """Delegate to QuestionManager."""
        game = await self._get_game(game_id)
        await self._get_question_manager(game).dismiss_question(game_id)
    
    async def change_buzzer_status(self, active: bool, game_id: str):
        """Change buzzer status and broadcast to all clients"""
        logger.debug(f"Setting buzzer status to: {active}")

        game = await self._get_game(game_id)
        game.buzzer_active = active

        buzzer_mgr = self._get_buzzer_manager(game)
        if active:
            await buzzer_mgr.activate_buzzer(game_id=game_id)
        else:
            await buzzer_mgr.deactivate_buzzer(game_id=game_id)
    
    async def register_player(self, websocket: WebSocket, name: str, preferences: str = '', game_id: str = ''):
        """Register a new player with the given name and preferences"""
        game = await self._get_game(game_id)
        state = game.state

        websocket_id = str(id(websocket))
        if state.register_contestant(websocket_id, name):
            # Store the player's preferences if provided
            if preferences:
                logger.info(f"Adding preferences from registration: {name}: {preferences}")
                if game.ai_host and hasattr(game.ai_host, 'game_state_manager'):
                    game.ai_host.game_state_manager.add_player_preference(name, preferences)

            # Broadcast updated player list
            await self.broadcast_player_list(game_id)

            # Check if we have enough players
            if len(state.contestants) >= self.REQUIRED_PLAYERS:
                game.game_ready = True
                await self.connection_manager.broadcast_message(
                    "com.sc2ctl.jeopardy.game_ready",
                    {"ready": True},
                    game_id=game_id
                )
            return True
        return False
    
    async def broadcast_player_list(self, game_id: str):
        """Send current player list to all clients"""
        game = await self._get_game(game_id)
        state = game.state

        # Get preferences if available
        player_prefs = {}
        if game.ai_host and hasattr(game.ai_host, 'game_state_manager'):
            player_prefs = game.ai_host.game_state_manager.player_preferences

        players = {
            c.name: {
                "score": c.score,
                "preferences": player_prefs.get(c.name, "")
            }
            for c in state.contestants.values()
        }
        await self.connection_manager.broadcast_message(
            "com.sc2ctl.jeopardy.player_list",
            {"players": players},
            game_id=game_id
        )
    
    async def handle_buzz(self, websocket: WebSocket, timestamp: float, game_id: str):
        """Handle a buzz from a contestant"""
        logger.debug(f"handle_buzz called with game_id: {game_id}")
        game = await self._get_game(game_id)
        state = game.state
        logger.debug(f"handle_buzz: game.buzzer_active={game.buzzer_active}")

        # Get client_id from connection manager
        client_id = self.connection_manager.get_client_id_for_websocket(websocket)
        logger.debug(f"handle_buzz: client_id from connection_manager: {client_id}")
        if not client_id:
            client_id = str(id(websocket))
            logger.debug(f"handle_buzz: fell back to object id: {client_id}")

        contestant = state.get_contestant_by_websocket(client_id)

        if not contestant:
            logger.warning(f"Contestant not found for websocket {client_id}")
            return

        logger.info(f"Buzz received from {contestant.name} at {timestamp}")

        if not game.buzzer_active:
            logger.warning(f"Buzz from {contestant.name} ignored - buzzer not active")
            return

        logger.info(f"Buzz accepted from {contestant.name}")

        # Use the buzzer manager to handle the buzz event
        await self._get_buzzer_manager(game).handle_player_buzz(contestant.name, game_id=game_id)

        # Notify all clients of the buzz
        await self.connection_manager.broadcast_message(
            self.BUZZER_TOPIC,
            {"contestant": contestant.name, "timestamp": timestamp},
            game_id=game_id
        )

        # Update LLM state for player buzzed in
        game.llm_state.player_buzzed_in(contestant.name)
    
    async def answer_question(self, correct: bool, contestant_name=None, game_id: str = ''):
        """Delegate to QuestionManager."""
        game = await self._get_game(game_id)
        await self._get_question_manager(game).answer_question(correct, contestant_name, game_id)

    async def handle_daily_double_bet(self, contestant: str, bet: int, game_id: str):
        """Delegate to QuestionManager."""
        game = await self._get_game(game_id)
        await self._get_question_manager(game).handle_daily_double_bet(contestant, bet, game_id)
    
    async def handle_final_jeopardy_request(self, content_type: str, game_id: str):
        """Handle a request for final jeopardy content"""
        game = await self._get_game(game_id)
        board = game.board
        clue = board.final_jeopardy_state.clue

        payload = {}
        if content_type == "category":
            payload = {"category": clue.category}
        elif content_type == "clue":
            payload = {"clue": clue.clue}
        elif content_type == "answer":
            payload = {"answer": clue.answer}

        await self.connection_manager.broadcast_message(
            self.FINAL_JEOPARDY_TOPIC,
            payload,
            game_id=game_id
        )

    async def handle_final_jeopardy_bet(self, contestant: str, bet: int, game_id: str):
        """Handle a final jeopardy bet"""
        game = await self._get_game(game_id)
        game.board.final_jeopardy_state.set_bet(contestant, bet)

    async def handle_final_jeopardy_answer(self, contestant: str, answer: str, game_id: str):
        """Handle a final jeopardy answer"""
        game = await self._get_game(game_id)
        game.board.final_jeopardy_state.set_answer(contestant, answer)

    async def request_final_jeopardy_bets(self, game_id: str):
        """Request final jeopardy bets from all contestants"""
        game = await self._get_game(game_id)
        board = game.board

        if not board:
            logger.warning("Cannot start Final Jeopardy - no board loaded")
            return

        # Get final jeopardy question
        final_jeopardy = board.final_jeopardy_state

        # Send category first
        await self.connection_manager.broadcast_message(
            self.FINAL_JEOPARDY_TOPIC,
            {"type": "category", "category": final_jeopardy.category},
            game_id=game_id
        )

        # Request bets
        await self.connection_manager.broadcast_message(
            self.FINAL_JEOPARDY_TOPIC,
            {"type": "bet"},
            game_id=game_id
        )

        # For each AI player, update their state to making a wager
        for contestant in game.state.contestants.values():
            game.llm_state.making_wager(
                player_name=contestant.name,
                wager_type="Final Jeopardy",
                max_wager=contestant.score
            )

    async def check_final_jeopardy_bets_after_timeout(self, game_id: str):
        """Check if all bets are received after timeout"""
        await asyncio.sleep(self.FINAL_JEOPARDY_COLLECTION_TIMEOUT)

        game = await self._get_game(game_id)
        if not game.board.final_jeopardy_state.has_all_bets():
            missing = game.board.final_jeopardy_state.get_missing_bets()
            logger.warning(f"Did not receive all final jeopardy bets! Missing: {', '.join(missing)}")

        # Show clue anyway
        await self.handle_final_jeopardy_request("clue", game_id)

    async def request_final_jeopardy_answers(self, game_id: str):
        """Request answers from all contestants"""
        await self.connection_manager.broadcast_message(
            self.FINAL_JEOPARDY_RESPONSES_TOPIC,
            {"content": "answer"},
            game_id=game_id
        )

        # Start timer to show answer anyway after timeout
        asyncio.create_task(self.check_final_jeopardy_answers_after_timeout(game_id))

    async def check_final_jeopardy_answers_after_timeout(self, game_id: str):
        """Check if all answers are received after timeout"""
        await asyncio.sleep(self.FINAL_JEOPARDY_COLLECTION_TIMEOUT)

        game = await self._get_game(game_id)
        if not game.board.final_jeopardy_state.has_all_answers():
            missing = game.board.final_jeopardy_state.get_missing_answers()
            logger.warning(f"Did not receive all final jeopardy answers! Missing: {', '.join(missing)}")

        # Show answer anyway
        await self.handle_final_jeopardy_request("answer", game_id)

    async def get_final_jeopardy_response(self, contestant: str, game_id: str):
        """Get a contestant's final jeopardy response"""
        game = await self._get_game(game_id)
        response = game.board.final_jeopardy_state.get_response(contestant)

        if not response:
            payload = {
                "contestant": contestant,
                "bet": 0,
                "answer": "No answer provided"
            }
        else:
            payload = response.dict()

        await self.connection_manager.broadcast_message(
            self.FINAL_JEOPARDY_ANSWER_TOPIC,
            payload,
            game_id=game_id
        )

    def find_contestant(self, name: str, state):
        """Find a contestant by name"""
        for contestant_id, contestant in state.contestants.items():
            if contestant.name == name:
                return contestant
        return None

    async def handle_audio_completed(self, audio_id: str, game_id: str):
        """Handle notification that audio playback has completed"""
        game = await self._get_game(game_id)

        # Mark the audio as completed
        game.mark_audio_completed(audio_id)

        # Delegate to buzzer manager
        logger.debug(f"Delegating audio_completed to buzzer_manager for game {game.game_code}")
        await self._get_buzzer_manager(game).handle_audio_completed(audio_id)

    async def handle_player_answer(self, contestant: str, answer: str, game_id: str):
        """Process a player's answer directly, bypassing chat classification."""
        game = await self._get_game(game_id)
        ai_host = game.ai_host
        if ai_host is None:
            logger.warning("AI host not available, cannot process player answer")
            return
        await ai_host.chat_processor.process_player_answer(contestant, answer)

    async def handle_chat_message(self, username: str, message: str, game_id: str):
        """
        Handle a chat message from a player and forward it to the AI host.

        Args:
            username: The player's username
            message: The chat message content
            game_id: Game ID for multi-game support
        """
        logger.info(f"Chat message from {username}: {message}")

        game = await self._get_game(game_id)
        ai_host = game.ai_host

        if ai_host is None:
            logger.warning("AI host not available, cannot process chat message")
            return

        # Store chat messages for preferences if in initial game phase
        if not game.game_ready and hasattr(ai_host, 'game_state_manager'):
            logger.debug(f"Directly storing chat message for preferences: {username}: {message}")
            ai_host.game_state_manager.recent_chat_messages.append({
                "username": username,
                "message": message
            })

        # Forward to AI host for processing
        await ai_host.process_chat_message(username, message)

    async def send_contestant_scores(self, game_id: str):
        """Send current contestant scores to all clients"""
        game = await self._get_game(game_id)
        scores = {
            contestant.name: contestant.score
            for contestant in game.state.contestants.values()
        }
        await self.connection_manager.broadcast_message(
            self.CONTESTANT_SCORE_TOPIC,
            {"scores": scores},
            game_id=game_id
        )

    async def play_audio(self, audio_url: str, wait_for_completion: bool = True, audio_id: str = None, game_id: str = ''):
        """
        Play audio on connected clients

        Args:
            audio_url: The URL of the audio file to play
            wait_for_completion: Whether to send a completion event when audio finishes
            audio_id: Optional unique ID for this audio playback
            game_id: Optional game ID to scope broadcast to specific game
        """
        # If no audio_id provided, try to extract it from the filename
        if not audio_id:
            # Try to extract timestamp from filename (e.g., question_audio_1234567890.wav)
            match = re.search(r'question_audio_(\d+)', audio_url)
            if match:
                # Use the timestamp from the filename
                audio_id = f"audio_{match.group(1)}"
            else:
                # Fallback to generating a new ID
                audio_id = f"audio_{int(time.time() * 1000)}"

        logger.debug(f"Broadcasting audio playback: {audio_url} (ID: {audio_id})")

        await self.connection_manager.broadcast_message(
            self.AUDIO_PLAY_TOPIC,
            {
                "audio_url": audio_url,
                "audio_id": audio_id,
                "wait_for_completion": wait_for_completion
            },
            game_id=game_id
        )

        return audio_id 