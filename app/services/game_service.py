from typing import Optional, Dict, Any, List
from fastapi import WebSocket
import asyncio
import time
from ..models.board import Board, BuzzerStatus, BuzzEvent
from ..models.question import Question
from ..models.contestant import Contestant
from ..models.finaljeopardy import FinalJeopardyQuestionResponse
from ..websockets.connection_manager import ConnectionManager
import logging
from ..models.game_state import GameStateManager
from ..ai.host import AIHostService
from ..ai.host.buzzer_manager import BuzzerManager
import json
import os
from pathlib import Path
import re

logging.basicConfig(level=logging.DEBUG)
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

        # Legacy single-game state (for backwards compatibility)
        self.board = None
        self.state = GameStateManager()
        self.current_question = None
        self.buzzer_active = False
        self.last_buzzer = None
        self.game_ready = False
        self.completed_audio_ids = set()

        # Legacy buzzer manager (for backwards compatibility)
        self.buzzer_manager = BuzzerManager()
        self.buzzer_manager.set_dependencies(game_service=self)

        # Legacy AI host service (for backwards compatibility)
        self.ai_host = AIHostService(name="AI Host")

    def set_game_manager(self, game_manager):
        """Set reference to game manager for multi-game lookups."""
        self.game_manager = game_manager

    async def _get_game_context(self, game_id: Optional[str]):
        """
        Get game-specific state or fall back to legacy single-game state.

        Returns tuple of (state, board, game_instance)
        """
        if game_id and self.game_manager:
            game = await self.game_manager.get_game_by_id(game_id)
            if game:
                logger.debug(f"_get_game_context: returning game {game.game_code} state (id: {game_id})")
                return game.state, game.board, game
            logger.warning(f"_get_game_context: game_id {game_id} not found, falling back to legacy state")
        elif game_id:
            logger.warning(f"_get_game_context: game_manager not set but game_id {game_id} provided")
        logger.debug(f"_get_game_context: returning legacy state (game_id was: {game_id})")
        return self.state, self.board, None

    def _get_buzzer_manager(self, game) -> BuzzerManager:
        """Get the appropriate buzzer manager for the game context."""
        if game and game._ai_host is not None:
            return game.ai_host.buzzer_manager
        return self.buzzer_manager  # Legacy fallback
    
    async def load_board(self, board_id: str):
        """Load a board from the filesystem"""
        try:
            board_path = self.boards_path / f"{board_id}.json"
            if not board_path.exists():
                logger.error(f"Board file not found: {board_path}")
                raise FileNotFoundError(f"Board {board_id} not found")

            logger.info(f"Loading board from {board_path}")
            with open(board_path, 'r') as f:
                board_data = json.load(f)
                # Make this our current board
                self.board = board_data
                logger.info(f"Successfully loaded board: {board_id}")
                
                # Game is ready when board is loaded
                self.game_ready = True
                
                return board_data

        except Exception as e:
            logger.error(f"Error loading board {board_id}: {e}")
            raise
    
    async def select_board(self, board_id: str, game_id: Optional[str] = None):
        """Load and initialize a new board"""
        try:
            board_data = await self.load_board(board_id)

            # Store board in appropriate location
            if game_id and self.game_manager:
                game = await self.game_manager.get_game_by_id(game_id)
                if game:
                    game.board = board_data

            self.board = board_data

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
    
    async def send_categories(self, game_id: Optional[str] = None):
        """Send all categories and questions to clients"""
        state, board, game = await self._get_game_context(game_id)

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
        if game:
            game.llm_state.update_categories(cat_names)
    
    def find_question(self, category_name: str, value: int, board=None):
        """Find a question in the specified board (or legacy self.board)"""
        target_board = board if board is not None else self.board
        if not target_board or "categories" not in target_board:
            logger.error("No board loaded or invalid board format")
            return None

        # Log all categories for debugging
        categories = [cat["name"] for cat in target_board["categories"]]
        logger.debug(f"Looking for '{category_name}' in categories: {categories}")

        # First try exact match
        for category in target_board["categories"]:
            if category["name"] == category_name:
                for question in category["questions"]:
                    if question["value"] == value:
                        return question

        # If no exact match, try case-insensitive match
        for category in target_board["categories"]:
            if category["name"].lower() == category_name.lower():
                logger.info(f"Found case-insensitive match for category: {category['name']}")
                for question in category["questions"]:
                    if question["value"] == value:
                        return question

        # If still no match, try partial match (contains)
        for category in target_board["categories"]:
            if (category_name.lower() in category["name"].lower() or
                category["name"].lower() in category_name.lower()):
                logger.info(f"Found partial match for category: '{category_name}' -> '{category['name']}'")
                for question in category["questions"]:
                    if question["value"] == value:
                        return question

        logger.error(f"No question found in category '{category_name}' with value ${value}")
        return None

    def mark_question_used(self, category_name: str, value: int, board=None):
        """Mark a question as used in the specified board (or legacy self.board)"""
        target_board = board if board is not None else self.board
        if not target_board or "categories" not in target_board:
            return

        for category in target_board["categories"]:
            if category["name"] == category_name:
                for question in category["questions"]:
                    if question["value"] == value:
                        question["used"] = True
                        break

    async def display_question(self, category_name: str, value: int, game_id: Optional[str] = None):
        """Display a question to all clients"""
        state, board, game = await self._get_game_context(game_id)
        game_ready = game.game_ready if game else self.game_ready

        if not game_ready:
            logger.warning("Cannot display question - waiting for players")
            await self.connection_manager.broadcast_message(
                "com.sc2ctl.jeopardy.error",
                {"message": f"Waiting for {self.REQUIRED_PLAYERS - len(state.contestants)} more players"},
                game_id=game_id
            )
            return

        try:
            question = self.find_question(category_name, value, board=board)
            if not question:
                logger.error(f"Question not found: {category_name} ${value}")
                return

            # Mark as used in the board data
            self.mark_question_used(category_name, value, board=board)
            
            # Reset buzzer state for new question
            if game:
                game.last_buzzer = None
                game.buzzer_active = False
            else:
                self.last_buzzer = None
                self.buzzer_active = False
            
            # Check if it's a daily double
            is_daily_double = question.get("daily_double", False)
            logger.info(f"Question is daily double: {is_daily_double}")
            
            # Set up the current question data
            question_data = {
                "category": category_name,
                "value": value,
                "text": question["clue"],
                "answer": question["answer"],
                "daily_double": is_daily_double
            }

            # Set current_question on game instance if available, otherwise on self
            if game:
                game.current_question = question_data
            else:
                self.current_question = question_data
            
            # Handle daily double differently
            if is_daily_double:
                # For daily double, we don't show the question yet
                # Just notify that it's a daily double
                logger.info(f"Broadcasting daily double: {category_name} ${value}")
                await self.connection_manager.broadcast_message(
                    "com.sc2ctl.jeopardy.daily_double",
                    {"category": category_name, "value": value},
                    game_id=game_id
                )
                logger.info(f"Displayed daily double: {category_name} ${value}")
            else:
                # For regular questions, proceed as normal
                logger.info(f"Broadcasting regular question: {category_name} ${value}")

                # Notify the BuzzerManager about the question display
                await self._get_buzzer_manager(game).handle_question_display()

                # Broadcast the question to all clients
                await self.connection_manager.broadcast_message(
                    self.QUESTION_DISPLAY_TOPIC,
                    question_data,
                    game_id=game_id
                )
                logger.info(f"Displayed question: {category_name} ${value}")
                
                # Update LLM state for AI players
                if game:
                    game.llm_state.question_displayed(
                        category=category_name,
                        value=value,
                        question_text=question["clue"]
                    )

        except Exception as e:
            logger.error(f"Error displaying question: {e}")
    
    async def dismiss_question(self, game_id: Optional[str] = None):
        """Dismiss the current question and broadcast to all clients"""
        logger.info("Dismissing question")

        state, board, game = await self._get_game_context(game_id)

        # Always ensure buzzer is deactivated when dismissing a question
        if game:
            game.buzzer_active = False
        else:
            self.buzzer_active = False
        await self._get_buzzer_manager(game).deactivate_buzzer(game_id=game_id)

        # Notify clients
        await self.connection_manager.broadcast_message(
            self.QUESTION_DISMISS_TOPIC,
            {},
            game_id=game_id
        )

        # Update LLM state
        if game:
            game.llm_state.question_dismissed()

        # Clear question state
        if game:
            game.current_question = None
            game.last_buzzer = None
        else:
            self.current_question = None
            self.last_buzzer = None
    
    async def change_buzzer_status(self, active: bool, game_id: Optional[str] = None):
        """Change buzzer status and broadcast to all clients"""
        logger.info(f"Setting buzzer status to: {active}")

        # Get game context
        state, board, game = await self._get_game_context(game_id)

        # Update game-specific state
        if game:
            game.buzzer_active = active

        # Use appropriate buzzer manager
        buzzer_mgr = self._get_buzzer_manager(game)
        if active:
            await buzzer_mgr.activate_buzzer(game_id=game_id)
        else:
            await buzzer_mgr.deactivate_buzzer(game_id=game_id)
    
    async def register_player(self, websocket: WebSocket, name: str, preferences: str = '', game_id: Optional[str] = None):
        """Register a new player with the given name and preferences"""
        state, board, game = await self._get_game_context(game_id)

        websocket_id = str(id(websocket))
        if state.register_contestant(websocket_id, name):
            # Store the player's preferences if provided
            if preferences:
                logger.info(f"Adding preferences from registration: {name}: {preferences}")

                # Store preferences in game-specific state manager
                if game and game.ai_host and hasattr(game.ai_host, 'game_state_manager'):
                    game.ai_host.game_state_manager.add_player_preference(name, preferences)
                elif hasattr(self, 'ai_host') and self.ai_host and hasattr(self.ai_host, 'game_state_manager'):
                    self.ai_host.game_state_manager.add_player_preference(name, preferences)

            # Broadcast updated player list
            await self.broadcast_player_list(game_id)

            # Check if we have enough players
            if len(state.contestants) >= self.REQUIRED_PLAYERS:
                if game:
                    game.game_ready = True
                else:
                    self.game_ready = True
                await self.connection_manager.broadcast_message(
                    "com.sc2ctl.jeopardy.game_ready",
                    {"ready": True},
                    game_id=game_id
                )
            return True
        return False
    
    async def broadcast_player_list(self, game_id: Optional[str] = None):
        """Send current player list to all clients"""
        state, board, game = await self._get_game_context(game_id)

        # Get preferences if available
        player_prefs = {}
        if game and game.ai_host and hasattr(game.ai_host, 'game_state_manager'):
            player_prefs = game.ai_host.game_state_manager.player_preferences
        elif hasattr(self, 'ai_host') and self.ai_host and hasattr(self.ai_host, 'game_state_manager'):
            player_prefs = self.ai_host.game_state_manager.player_preferences

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
    
    async def handle_buzz(self, websocket: WebSocket, timestamp: float, game_id: Optional[str] = None):
        """Handle a buzz from a contestant"""
        logger.info(f"handle_buzz called with game_id: {game_id}")
        state, board, game = await self._get_game_context(game_id)
        if game:
            logger.info(f"handle_buzz: game obj_id={id(game)}, game.buzzer_active={game.buzzer_active}")
        buzzer_active = game.buzzer_active if game else self.buzzer_active

        # Get client_id from connection manager
        client_id = self.connection_manager.get_client_id_for_websocket(websocket)
        logger.info(f"handle_buzz: client_id from connection_manager: {client_id}")
        if not client_id:
            client_id = str(id(websocket))
            logger.info(f"handle_buzz: fell back to object id: {client_id}")

        contestant = state.get_contestant_by_websocket(client_id)

        if not contestant:
            logger.warning(f"Contestant not found for websocket {client_id}")
            return

        logger.info(f"Buzz received from {contestant.name} at {timestamp}")

        if not buzzer_active:
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
        if game:
            game.llm_state.player_buzzed_in(contestant.name)
    
    async def answer_question(self, correct: bool, contestant_name=None, game_id: Optional[str] = None):
        """Handle an answer from a contestant"""
        state, board, game = await self._get_game_context(game_id)
        current_question = game.current_question if game else self.current_question
        last_buzzer = game.last_buzzer if game else self.last_buzzer

        if not current_question:
            logger.warning("No current question to answer")
            return

        # If no contestant name provided, use the last person to buzz in
        if not contestant_name:
            contestant_name = last_buzzer

        if not contestant_name:
            logger.warning("No contestant to score")
            return

        logger.info(f"Processing answer from {contestant_name}: {'correct' if correct else 'incorrect'}")

        score_delta = current_question["value"]
        daily_double = current_question.get("daily_double", False)

        contestant = self.find_contestant(contestant_name, state=state)
        if not contestant:
            logger.warning(f"Contestant {contestant_name} not found")
            return

        # Broadcast the answer result
        await self.connection_manager.broadcast_message(
            self.QUESTION_ANSWER_TOPIC,
            {
                "contestant": contestant_name,
                "correct": correct,
                "value": score_delta,
                "answer": current_question["answer"]
            },
            game_id=game_id
        )
            
        # Handle correct answer
        if correct:
            logger.info(f"Correct answer from {contestant_name}")

            # Award points
            contestant.score += score_delta

            # Use the buzzer manager to handle the correct answer
            await self._get_buzzer_manager(game).handle_correct_answer(contestant_name)
            
            # If this was a daily double or all questions have been answered, we're done
            if daily_double or self.all_questions_answered(board=board):
                await self.dismiss_question(game_id=game_id)
            else:
                # Let the contestant choose the next question
                await self.connection_manager.broadcast_message(
                    "com.sc2ctl.jeopardy.select_question",
                    {"contestant": contestant_name},
                    game_id=game_id
                )

                # Update LLM state for selecting question
                if game:
                    game.llm_state.selecting_question(contestant_name)

            # Broadcast score update
            await self.send_contestant_scores(game_id)

            # Update LLM state with new score
            if game:
                game.llm_state.update_player_score(contestant_name, contestant.score)

        # Handle incorrect answer
        else:
            logger.info(f"Incorrect answer from {contestant_name}")

            # Deduct points for incorrect answers
            contestant.score -= score_delta

            # Use the buzzer manager to handle incorrect answer
            await self._get_buzzer_manager(game).handle_incorrect_answer(contestant_name)

            # Broadcast score update
            await self.send_contestant_scores(game_id)

            # Update LLM state with new score
            if game:
                game.llm_state.update_player_score(contestant_name, contestant.score)

    async def handle_daily_double_bet(self, contestant: str, bet: int, game_id: Optional[str] = None):
        """Handle a daily double bet from a contestant"""
        logger.info(f"Daily double bet: {contestant} bets ${bet}")

        state, board, game = await self._get_game_context(game_id)
        current_question = game.current_question if game else self.current_question

        if not current_question:
            logger.warning("No current question for daily double bet")
            return

        # Validate bet is within allowed range
        player = self.find_contestant(contestant, state=state)
        if not player:
            logger.warning(f"Contestant {contestant} not found")
            return
            
        max_bet = max(1000, player.score)
        if bet < 5 or bet > max_bet:
            logger.warning(f"Invalid bet amount: ${bet}. Must be between $5 and ${max_bet}")
            return
            
        # Store bet amount and contestant in current question
        current_question["value"] = bet
        current_question["contestant"] = contestant

        # First send a response to confirm the bet was placed
        await self.connection_manager.broadcast_message(
            "com.sc2ctl.jeopardy.daily_double_bet_response",
            {
                "question": current_question,
                "bet": bet,
                "contestant": contestant
            },
            game_id=game_id
        )

        # Then display the question after the bet is confirmed
        await self.connection_manager.broadcast_message(
            self.QUESTION_DISPLAY_TOPIC,
            current_question,
            game_id=game_id
        )

        # For daily doubles, the contestant who selected it automatically gets to answer
        # So we don't activate the buzzer for everyone
        if game:
            game.last_buzzer = contestant
        else:
            self.last_buzzer = contestant

        # Update LLM state
        if game:
            game.llm_state.question_displayed(
                category=current_question["category"],
                value=bet,
                question_text=current_question["text"]
            )

            # After showing the question, the next step is for the player to answer
            game.llm_state.player_buzzed_in(contestant)
    
    async def handle_final_jeopardy_request(self, content_type: str):
        """Handle a request for final jeopardy content"""
        clue = self.board.final_jeopardy_state.clue
        
        payload = {}
        if content_type == "category":
            payload = {"category": clue.category}
        elif content_type == "clue":
            payload = {"clue": clue.clue}
        elif content_type == "answer":
            payload = {"answer": clue.answer}
        
        await self.connection_manager.broadcast_to_topic(
            self.FINAL_JEOPARDY_TOPIC,
            {
                "topic": self.FINAL_JEOPARDY_TOPIC,
                "payload": payload
            }
        )
    
    async def handle_final_jeopardy_bet(self, contestant: str, bet: int):
        """Handle a final jeopardy bet"""
        self.board.final_jeopardy_state.set_bet(contestant, bet)
    
    async def handle_final_jeopardy_answer(self, contestant: str, answer: str):
        """Handle a final jeopardy answer"""
        self.board.final_jeopardy_state.set_answer(contestant, answer)
    
    async def request_final_jeopardy_bets(self):
        """Request final jeopardy bets from all contestants"""
        if not self.board:
            logger.warning("Cannot start Final Jeopardy - no board loaded")
            return
            
        # Get final jeopardy question
        final_jeopardy = self.board.final_jeopardy_state
        
        # Send category first
        await self.connection_manager.broadcast_message(
            self.FINAL_JEOPARDY_TOPIC,
            {"type": "category", "category": final_jeopardy.category}
        )
        
        # Request bets
        await self.connection_manager.broadcast_message(
            self.FINAL_JEOPARDY_TOPIC,
            {"type": "bet"}
        )
        
        # For each AI player, update their state to making a wager
        for contestant in self.board.contestants:
            # Update LLM state for making wager
            self.llm_state.making_wager(
                player_name=contestant.name,
                wager_type="Final Jeopardy",
                max_wager=contestant.score
            )
    
    async def check_final_jeopardy_bets_after_timeout(self):
        """Check if all bets are received after timeout"""
        await asyncio.sleep(self.FINAL_JEOPARDY_COLLECTION_TIMEOUT)
        
        if not self.board.final_jeopardy_state.has_all_bets():
            missing = self.board.final_jeopardy_state.get_missing_bets()
            print(f"Did not receive all final jeopardy bets! Missing: {', '.join(missing)}")
        
        # Show clue anyway
        await self.handle_final_jeopardy_request("clue")
    
    async def request_final_jeopardy_answers(self):
        """Request answers from all contestants"""
        await self.connection_manager.broadcast_to_topic(
            self.FINAL_JEOPARDY_RESPONSES_TOPIC,
            {
                "topic": self.FINAL_JEOPARDY_RESPONSES_TOPIC,
                "payload": {"content": "answer"}
            }
        )
        
        # Start timer to show answer anyway after timeout
        asyncio.create_task(self.check_final_jeopardy_answers_after_timeout())
    
    async def check_final_jeopardy_answers_after_timeout(self):
        """Check if all answers are received after timeout"""
        await asyncio.sleep(self.FINAL_JEOPARDY_COLLECTION_TIMEOUT)
        
        if not self.board.final_jeopardy_state.has_all_answers():
            missing = self.board.final_jeopardy_state.get_missing_answers()
            print(f"Did not receive all final jeopardy answers! Missing: {', '.join(missing)}")
        
        # Show answer anyway
        await self.handle_final_jeopardy_request("answer")
    
    async def get_final_jeopardy_response(self, contestant: str):
        """Get a contestant's final jeopardy response"""
        response = self.board.final_jeopardy_state.get_response(contestant)
        
        if not response:
            # No answer provided
            payload = {
                "contestant": contestant,
                "bet": 0,
                "answer": "No answer provided"
            }
        else:
            payload = response.dict()
        
        await self.connection_manager.broadcast_to_topic(
            self.FINAL_JEOPARDY_ANSWER_TOPIC,
            {
                "topic": self.FINAL_JEOPARDY_ANSWER_TOPIC,
                "payload": payload
            }
        )

    async def send_game_state(self, websocket: WebSocket):
        """Send current game state to new connection"""
        if self.board:
            await self.connection_manager.send_personal_message(
                websocket,
                "com.sc2ctl.jeopardy.board_selected",
                {"categories": self.board["categories"]}
            )
        
        if self.current_question:
            await self.connection_manager.send_personal_message(
                websocket,
                self.QUESTION_DISPLAY_TOPIC,
                self.current_question
            )
        
        await self.connection_manager.send_personal_message(
            websocket,
            self.BUZZER_STATUS_TOPIC,
            {"active": self.buzzer_active}
        )

    def find_contestant(self, name: str, state=None):
        """Find a contestant by name"""
        if state is None:
            state = self.state
        for contestant_id, contestant in state.contestants.items():
            if contestant.name == name:
                return contestant
        return None

    def all_questions_answered(self, board=None) -> bool:
        """Check if all questions have been answered in the specified board (or legacy self.board)"""
        target_board = board if board is not None else self.board
        if not target_board or "categories" not in target_board:
            return False

        for category in target_board["categories"]:
            for question in category["questions"]:
                if not question.get("used", False):
                    return False
        return True

    def mark_audio_completed(self, audio_id: str):
        """Mark an audio file as having completed playback"""
        logger.info(f"🔊 Marking audio as completed: {audio_id}")
        self.completed_audio_ids.add(audio_id)
        logger.debug(f"Current completed audio IDs: {list(self.completed_audio_ids)[:5]}...")
        
        # Clean up old IDs if there are too many (keep last 100)
        if len(self.completed_audio_ids) > 100:
            # Convert to list, sort by timestamp part of ID, and keep only most recent 100
            sorted_ids = sorted(
                self.completed_audio_ids, 
                key=lambda x: int(x.split('_')[-1]) if '_' in x and x.split('_')[-1].isdigit() else 0,
                reverse=True
            )
            self.completed_audio_ids = set(sorted_ids[:100])
        
        # Use the buzzer manager to handle audio completion
        asyncio.create_task(self.buzzer_manager.handle_audio_completed(audio_id))

    def check_audio_completed(self, audio_id: str) -> bool:
        """Check if an audio file has completed playback"""
        result = audio_id in self.completed_audio_ids
        logger.debug(f"Checking if audio {audio_id} completed: {result}")
        return result

    async def handle_audio_completed(self, audio_id: str, game_id: Optional[str] = None):
        """Handle notification that audio playback has completed"""
        state, board, game = await self._get_game_context(game_id)

        # Mark the audio as completed
        if game:
            game.mark_audio_completed(audio_id)
        else:
            self.mark_audio_completed(audio_id)

        # Delegate to appropriate buzzer manager
        logger.info(f"Delegating audio_completed to buzzer_manager for game {game.game_code if game else 'legacy'}")
        await self._get_buzzer_manager(game).handle_audio_completed(audio_id)

    async def startup(self):
        """Initialize the game service (stateless dispatcher).

        AI host startup is handled per-game in GameInstance.start_ai_host().
        """
        logger.info("Game service initialized")
        return True

    async def handle_chat_message(self, username: str, message: str, game_id: Optional[str] = None):
        """
        Handle a chat message from a player and forward it to the AI host.

        Args:
            username: The player's username
            message: The chat message content
            game_id: Optional game ID for multi-game support
        """
        logger.info(f"Chat message from {username}: {message}")

        # Get the correct AI host for this game
        ai_host = None
        if game_id and self.game_manager:
            game = await self.game_manager.get_game_by_id(game_id)
            if game and game._ai_host is not None:
                ai_host = game.ai_host

        # Fall back to legacy single-game AI host
        if ai_host is None:
            ai_host = getattr(self, 'ai_host', None)

        if ai_host is None:
            logger.warning("AI host not available, cannot process chat message")
            return

        # Store chat messages for preferences if in initial game phase
        if not self.game_ready and hasattr(ai_host, 'game_state_manager'):
            logger.info(f"Directly storing chat message for preferences: {username}: {message}")
            ai_host.game_state_manager.recent_chat_messages.append({
                "username": username,
                "message": message
            })

        # Forward to AI host for processing
        await ai_host.process_chat_message(username, message)

    async def dismiss_current_question(self):
        """Dismiss the current question and notify all clients"""
        if self.current_question:
            # Mark the question as used
            category = self.current_question["category"]
            value = self.current_question["value"]
            
            # Find and mark the question as used
            for cat in self.board.categories:
                if cat.name == category:
                    for question in cat.questions:
                        if question.value == value:
                            question.used = True
                            break
        
        # Call our main dismiss_question method to handle the rest
        await self.dismiss_question()

    async def send_buzzer_status(self):
        """Send current buzzer status to all clients"""
        await self.connection_manager.broadcast_message(
            self.BUZZER_STATUS_TOPIC,
            {"active": self.buzzer_active}
        )

    async def send_contestant_scores(self, game_id: Optional[str] = None):
        """Send current contestant scores to all clients"""
        state, board, game = await self._get_game_context(game_id)
        scores = {
            contestant.name: contestant.score
            for contestant in state.contestants.values()
        }
        await self.connection_manager.broadcast_message(
            self.CONTESTANT_SCORE_TOPIC,
            {"scores": scores},
            game_id=game_id
        )

    async def play_audio(self, audio_url: str, wait_for_completion: bool = True, audio_id: str = None, game_id: str = None):
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

        logger.info(f"🔊 Broadcasting audio playback: {audio_url} (ID: {audio_id}, wait: {wait_for_completion}, game: {game_id})")

        # Support both message formats - keep as 'url' for backward compatibility with existing UI code
        # but also include as audio_url for newer code
        await self.connection_manager.broadcast_message(
            self.AUDIO_PLAY_TOPIC,
            {
                "url": audio_url,  # For backward compatibility
                "audio_url": audio_url,  # For newer code
                "audio_id": audio_id,
                "wait_for_completion": wait_for_completion
            },
            game_id=game_id
        )

        return audio_id 