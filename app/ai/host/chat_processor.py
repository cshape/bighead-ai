"""
Chat message processing for AI host
"""

import logging
import asyncio
import os
import re
from typing import Optional, Set, Dict, Any
from datetime import datetime

from .utils.helpers import is_same_player

logger = logging.getLogger(__name__)

class ChatProcessor:
    """
    Processes chat messages for the AI host.

    Handles parsing and classification of player chat messages
    to determine appropriate host responses.
    """

    def __init__(self):
        """Initialize the chat processor."""
        self.host_name = None
        self.game_service = None
        self.game_state_manager = None
        self.answer_evaluator = None
        self.game_instance = None

    def set_host_name(self, name: str):
        """Set the host name for chat messages."""
        self.host_name = name

    def set_dependencies(self, game_service, game_state_manager, answer_evaluator, game_instance=None):
        """Set dependencies required for chat processing."""
        self.game_service = game_service
        self.game_state_manager = game_state_manager
        self.answer_evaluator = answer_evaluator
        self.game_instance = game_instance

    @property
    def _game_id(self):
        """Get the game_id from the game instance."""
        return self.game_instance.game_id

    async def send_chat_message(self, message: str):
        """Send a chat message as the AI host."""
        if not self.game_service:
            logger.error("Cannot send chat message: Game service not set")
            return False

        try:
            chat_payload = {
                "username": self.host_name,
                "message": message,
                "isHost": True,
                "timestamp": datetime.now().isoformat(),
                "is_admin": True
            }

            await self.game_service.connection_manager.broadcast_message(
                "com.sc2ctl.jeopardy.chat_message",
                chat_payload,
                game_id=self._game_id
            )

            logger.info(f"AI host ({self.host_name}) sent message: {message}")
            return True

        except Exception as e:
            logger.error(f"Error sending chat message: {e}")
            return False

    async def process_chat_message(self, username: str, message: str):
        """
        Process a chat message from a player.

        Args:
            username: The player's username
            message: The content of the chat message
        """
        logger.debug(f"Processing chat message from {username}: {message}")

        # Skip processing messages from the host itself
        if is_same_player(username, self.host_name):
            logger.debug(f"Skipping host message: {message}")
            return

        # Check if we're in the preference collection phase
        if self.game_state_manager.is_waiting_for_preferences():
            logger.debug(f"Adding message from {username} to preference collection")
            self.game_state_manager.add_chat_message(username, message)
            return

        # Log detailed game state for debugging
        buzzed_player = self.game_state_manager.get_buzzed_player()
        controlling_player = self.game_state_manager.get_player_with_control()

        logger.debug(f"Game state - buzzed_player: {buzzed_player}, controlling_player: {controlling_player}")
        logger.debug(f"Current question in game state: {self.game_state_manager.game_state.current_question is not None}")
        logger.debug(f"Game instance - current_question: {self.game_instance.current_question is not None}")
        logger.debug(f"Game instance - last_buzzer: {self.game_instance.last_buzzer}")

        # Determine if there's currently an active question
        has_active_question = (
            self.game_state_manager.game_state.current_question is not None
            or self.game_instance.current_question is not None
        )

        logger.debug(f"Final active question determination: {has_active_question}")

        # Check if this player has buzzed in and if there's an active question
        if has_active_question and buzzed_player and is_same_player(username, buzzed_player):
            logger.debug(f"Processing as answer from buzzed player: {username}")
            await self.process_player_answer(username, message)
            return

        logger.debug(f"Message not processed for action: {username}: {message}")

    async def process_player_answer(self, username: str, message: str):
        """
        Process an answer from a player who has buzzed in.

        Args:
            username: The player who buzzed in
            message: The player's answer
        """
        logger.debug(f"Processing answer from {username}: {message}")

        try:
            # Cancel the answer timeout immediately — the player has submitted an answer,
            # so we must not let the timeout fire while the AI evaluates it.
            if (self.game_instance and self.game_instance.ai_host
                    and self.game_instance.ai_host.buzzer_manager):
                self.game_instance.ai_host.buzzer_manager.cancel_answer_timeout()
                logger.debug("Cancelled answer timeout — player submitted answer")

            # Notify frontend to stop the answer timer visual
            if self.game_service:
                await self.game_service.connection_manager.broadcast_message(
                    "com.sc2ctl.jeopardy.answer_timer_stop",
                    {},
                    game_id=self._game_id
                )

            # Get the current question
            question = self.game_state_manager.game_state.current_question
            if not question:
                logger.warning(f"No active question found when processing answer from {username}")
                return

            expected_answer = question.get("answer", "")
            if not expected_answer:
                logger.warning("No expected answer found for current question")
                return

            # Check player answer against expected answer
            evaluation_result = await self.answer_evaluator.evaluate_answer(
                expected_answer=expected_answer,
                player_answer=message,
                include_explanation=False
            )

            is_correct = evaluation_result.get("is_correct", False)
            explanation = evaluation_result.get("explanation", "")

            # Send appropriate response based on correctness
            test_mode = os.environ.get("TEST_MODE")

            if is_correct:
                correct_msg = f"That's correct, {username}! {explanation}"
                logger.info(f"Player {username} answered correctly")
                await self.send_chat_message(correct_msg)

                # If possible, provide audio feedback
                if not test_mode and self.game_instance and self.game_instance.ai_host and hasattr(self.game_instance.ai_host, "audio_manager"):
                    await self.game_instance.ai_host.audio_manager.synthesize_and_play_speech(correct_msg)
            else:
                incorrect_msg = f"I'm sorry, {username}, that's incorrect. {explanation}"
                logger.info(f"Player {username} answered incorrectly")
                await self.send_chat_message(incorrect_msg)

                # If possible, provide audio feedback
                if not test_mode and self.game_instance and self.game_instance.ai_host and hasattr(self.game_instance.ai_host, "audio_manager"):
                    try:
                        await self.game_instance.ai_host.audio_manager.synthesize_and_play_speech(incorrect_msg, is_incorrect_answer_audio=True)
                    except TypeError as e:
                        logger.error(f"Error synthesizing incorrect answer speech: {e}")
                        logger.info("Falling back to regular speech synthesis without incorrect answer flag")
                        await self.game_instance.ai_host.audio_manager.synthesize_and_play_speech(incorrect_msg)
                    except Exception as e:
                        logger.error(f"Error synthesizing speech: {e}")

            # Notify the game service to update scores and UI
            logger.debug(f"Notifying game service about answer: player={username}, correct={is_correct}, game_id={self._game_id}")
            await self.game_service.answer_question(is_correct, username, game_id=self._game_id)

            # For correct answers, explicitly dismiss the question to ensure clean state
            if is_correct:
                logger.debug("Explicitly dismissing question after correct answer")
                await self.game_service.dismiss_question(game_id=self._game_id)

            # Reset our state
            if is_correct:
                self.game_state_manager.reset_buzzed_player()
                logger.debug(f"Reset buzzed player state after correct answer from {username}")

                self.game_state_manager.reset_question()

                # Give control to the player who answered correctly
                self.game_state_manager.set_player_with_control(username, set())
                logger.debug(f"Player {username} gets control of the board")

                # Small delay to allow UI to update before prompting for next selection
                await asyncio.sleep(0.5)

                next_selection_msg = f"{username}, you have control of the board!"
                await self.send_chat_message(next_selection_msg)

            else:
                # For incorrect answers, track the player who answered
                self.game_state_manager.track_incorrect_attempt(username)
                self.game_state_manager.reset_buzzed_player()

                # Reset buzzer state to allow others to buzz in
                self.game_instance.last_buzzer = None
                logger.debug("Reset game instance buzzer state after incorrect answer")

                # Reactivate buzzer for remaining players
                if self.game_instance.current_question:
                    if test_mode:
                        # TEST_MODE: directly reactivate buzzer instead of waiting for audio
                        logger.info("TEST_MODE: Directly reactivating buzzer after incorrect answer")
                        if self.game_instance and self.game_instance.ai_host and self.game_instance.ai_host.buzzer_manager:
                            bm = self.game_instance.ai_host.buzzer_manager
                            bm.expecting_reactivation = False
                            await bm.activate_buzzer(game_id=self._game_id)
                    else:
                        logger.debug("Will reactivate buzzer AFTER incorrect answer audio plays")
                        if self.game_instance and self.game_instance.ai_host and self.game_instance.ai_host.buzzer_manager:
                            self.game_instance.ai_host.buzzer_manager.expecting_reactivation = True
                            logger.debug("Setting buzzer_manager.expecting_reactivation = True")

        except Exception as e:
            logger.error(f"Error processing player answer: {e}")
            import traceback
            logger.error(traceback.format_exc())

