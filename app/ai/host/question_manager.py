"""
QuestionManager - owns question display, dismiss, answer, and daily double logic.

Extracted from GameService to clarify ownership: AIHost components own game logic,
GameService acts as a thin broadcaster.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class QuestionManager:
    """
    Manages question lifecycle: find, display, dismiss, answer, daily doubles.
    """

    def __init__(self):
        self.game_service = None
        self.game_instance = None
        self.buzzer_manager = None

    def set_dependencies(self, game_service=None, game_instance=None, buzzer_manager=None):
        if game_service:
            self.game_service = game_service
        if game_instance:
            self.game_instance = game_instance
        if buzzer_manager:
            self.buzzer_manager = buzzer_manager

    def _get_game_id(self) -> Optional[str]:
        return self.game_instance.game_id if self.game_instance else None

    # ------------------------------------------------------------------
    # Question lookup
    # ------------------------------------------------------------------

    def find_question(self, category_name: str, value: int, board):
        """Find a question in the specified board."""
        if not board or "categories" not in board:
            logger.error("No board loaded or invalid board format")
            return None

        categories = [cat["name"] for cat in board["categories"]]
        logger.debug(f"Looking for '{category_name}' in categories: {categories}")

        # Exact match
        for category in board["categories"]:
            if category["name"] == category_name:
                for question in category["questions"]:
                    if question["value"] == value:
                        return question

        # Case-insensitive
        for category in board["categories"]:
            if category["name"].lower() == category_name.lower():
                logger.debug(f"Found case-insensitive match for category: {category['name']}")
                for question in category["questions"]:
                    if question["value"] == value:
                        return question

        # Partial match
        for category in board["categories"]:
            if (category_name.lower() in category["name"].lower() or
                    category["name"].lower() in category_name.lower()):
                logger.debug(f"Found partial match for category: '{category_name}' -> '{category['name']}'")
                for question in category["questions"]:
                    if question["value"] == value:
                        return question

        logger.error(f"No question found in category '{category_name}' with value ${value}")
        return None

    def mark_question_used(self, category_name: str, value: int, board):
        """Mark a question as used in the specified board."""
        if not board or "categories" not in board:
            return

        for category in board["categories"]:
            if category["name"] == category_name:
                for question in category["questions"]:
                    if question["value"] == value:
                        question["used"] = True
                        break

    def all_questions_answered(self, board) -> bool:
        """Check if all questions have been answered."""
        if not board or "categories" not in board:
            return False

        for category in board["categories"]:
            for question in category["questions"]:
                if not question.get("used", False):
                    return False
        return True

    def get_unused_clues(self, board):
        """Return list of (category_name, value) tuples for all unused questions."""
        unused = []
        if not board or "categories" not in board:
            return unused
        for category in board["categories"]:
            for question in category["questions"]:
                if not question.get("used", False):
                    unused.append((category["name"], question["value"]))
        return unused

    # ------------------------------------------------------------------
    # Display / Dismiss
    # ------------------------------------------------------------------

    async def display_question(self, category_name: str, value: int, game_id: str):
        """Display a question to all clients."""
        game = self.game_instance
        if not game:
            game = await self.game_service._get_game(game_id)

        board = game.board
        state = game.state

        if not game.game_ready:
            logger.warning("Cannot display question - waiting for players")
            await self.game_service.connection_manager.broadcast_message(
                "com.sc2ctl.bighead.error",
                {"message": f"Waiting for more players"},
                game_id=game_id
            )
            return

        try:
            question = self.find_question(category_name, value, board)
            if not question:
                logger.error(f"Question not found: {category_name} ${value}")
                return

            self.mark_question_used(category_name, value, board)

            # Reset buzzer state for new question
            game.last_buzzer = None
            game.buzzer_active = False

            is_double_big_head = question.get("double_big_head", False)
            logger.debug(f"Question is daily double: {is_double_big_head}")

            question_data = {
                "category": category_name,
                "value": value,
                "text": question["clue"],
                "answer": question["answer"],
                "double_big_head": is_double_big_head
            }

            game.current_question = question_data

            if is_double_big_head:
                logger.info(f"Broadcasting daily double: {category_name} ${value}")
                await self.game_service.connection_manager.broadcast_message(
                    "com.sc2ctl.bighead.double_big_head",
                    {
                        "category": category_name,
                        "value": value,
                        "selecting_player": (
                            game.ai_host.game_state_manager.get_player_with_control()
                            if game.ai_host and game.ai_host.game_state_manager
                            else None
                        )
                    },
                    game_id=game_id
                )
            else:
                logger.debug(f"Broadcasting regular question: {category_name} ${value}")

                bm = self.buzzer_manager or self.game_service._get_buzzer_manager(game)
                await bm.handle_question_display()

                await self.game_service.connection_manager.broadcast_message(
                    self.game_service.QUESTION_DISPLAY_TOPIC,
                    question_data,
                    game_id=game_id
                )
                logger.info(f"Displayed question: {category_name} ${value}")

                game.llm_state.question_displayed(
                    category=category_name,
                    value=value,
                    question_text=question["clue"]
                )
        except Exception as e:
            logger.error(f"Error displaying question: {e}")

    async def dismiss_question(self, game_id: str):
        """Dismiss the current question and broadcast to all clients."""
        logger.info("Dismissing question")

        game = self.game_instance
        if not game:
            game = await self.game_service._get_game(game_id)

        bm = self.buzzer_manager or self.game_service._get_buzzer_manager(game)

        game.buzzer_active = False
        await bm.deactivate_buzzer(game_id=game_id)

        bm.last_buzzer = None
        bm.incorrect_players.clear()
        bm.expecting_reactivation = False

        if game.ai_host and game.ai_host.game_state_manager:
            game.ai_host.game_state_manager.reset_question()

        await self.game_service.connection_manager.broadcast_message(
            self.game_service.QUESTION_DISMISS_TOPIC,
            {},
            game_id=game_id
        )

        game.llm_state.question_dismissed()
        game.current_question = None
        game.last_buzzer = None

        # Check if all questions have been answered — trigger game completion
        if self.all_questions_answered(game.board):
            await self._complete_game(game, game_id)

    async def _complete_game(self, game, game_id: str):
        """Handle game completion: set status, broadcast results, stop AI host."""
        game.complete_game()

        # Build final scores
        scores = {c.name: c.score for c in game.state.contestants.values()}
        winner = max(scores, key=scores.get) if scores else None
        winner_score = scores.get(winner, 0) if winner else 0

        # Broadcast game_completed message
        await self.game_service.connection_manager.broadcast_message(
            "com.sc2ctl.bighead.game_completed",
            {"scores": scores, "winner": winner, "winner_score": winner_score},
            game_id=game_id
        )

        # Send congratulations chat message + TTS
        congrats_msg = f"Congratulations, {winner}! You won Big Head with ${winner_score}!"
        if game.ai_host and game.ai_host.chat_processor:
            await game.ai_host.chat_processor.send_chat_message(congrats_msg)
        if game.ai_host and game.ai_host.audio_manager and not os.environ.get("TEST_MODE"):
            await game.ai_host.audio_manager.synthesize_and_stream_speech(congrats_msg)

        # Stop the AI host task
        await game.stop_ai_host()

    # ------------------------------------------------------------------
    # Answer / Double Big Head Bet
    # ------------------------------------------------------------------

    async def answer_question(self, correct: bool, contestant_name=None, game_id: str = ''):
        """Handle an answer from a contestant."""
        game = self.game_instance
        if not game:
            game = await self.game_service._get_game(game_id)

        state = game.state
        board = game.board
        current_question = game.current_question
        last_buzzer = game.last_buzzer

        if not current_question:
            logger.warning("No current question to answer")
            return

        if not contestant_name:
            contestant_name = last_buzzer
        if not contestant_name:
            logger.warning("No contestant to score")
            return

        logger.info(f"Processing answer from {contestant_name}: {'correct' if correct else 'incorrect'}")

        score_delta = current_question["value"]
        double_big_head = current_question.get("double_big_head", False)

        contestant = self.game_service.find_contestant(contestant_name, state=state)
        if not contestant:
            logger.warning(f"Contestant {contestant_name} not found")
            return

        await self.game_service.connection_manager.broadcast_message(
            self.game_service.QUESTION_ANSWER_TOPIC,
            {
                "contestant": contestant_name,
                "correct": correct,
                "value": score_delta,
                "answer": current_question["answer"]
            },
            game_id=game_id
        )

        bm = self.buzzer_manager or self.game_service._get_buzzer_manager(game)

        if correct:
            logger.info(f"Correct answer from {contestant_name}")
            contestant.score += score_delta
            await bm.handle_correct_answer(contestant_name)

            if double_big_head or self.all_questions_answered(board):
                await self.dismiss_question(game_id=game_id)
            else:
                await self.game_service.connection_manager.broadcast_message(
                    "com.sc2ctl.bighead.select_question",
                    {"contestant": contestant_name},
                    game_id=game_id
                )
                game.llm_state.selecting_question(contestant_name)

            await self.game_service.send_contestant_scores(game_id)
            game.llm_state.update_player_score(contestant_name, contestant.score)
        else:
            logger.info(f"Incorrect answer from {contestant_name}")
            contestant.score -= score_delta
            await bm.handle_incorrect_answer(contestant_name)

            await self.game_service.send_contestant_scores(game_id)
            game.llm_state.update_player_score(contestant_name, contestant.score)

    async def handle_double_big_head_bet(self, contestant: str, bet: int, game_id: str):
        """Handle a daily double bet from a contestant."""
        logger.info(f"Double Big Head bet: {contestant} bets ${bet}")

        game = self.game_instance
        if not game:
            game = await self.game_service._get_game(game_id)

        state = game.state
        current_question = game.current_question

        if not current_question:
            logger.warning("No current question for daily double bet")
            return

        player = self.game_service.find_contestant(contestant, state=state)
        if not player:
            logger.warning(f"Contestant {contestant} not found")
            return

        max_bet = max(1000, player.score)
        if bet < 5 or bet > max_bet:
            logger.warning(f"Invalid bet amount: ${bet}. Must be between $5 and ${max_bet}")
            return

        current_question["value"] = bet
        current_question["contestant"] = contestant

        await self.game_service.connection_manager.broadcast_message(
            "com.sc2ctl.bighead.double_big_head_bet_response",
            {
                "question": current_question,
                "bet": bet,
                "contestant": contestant
            },
            game_id=game_id
        )

        await self.game_service.connection_manager.broadcast_message(
            self.game_service.QUESTION_DISPLAY_TOPIC,
            current_question,
            game_id=game_id
        )

        game.last_buzzer = contestant

        game.llm_state.question_displayed(
            category=current_question["category"],
            value=bet,
            question_text=current_question["text"]
        )
        game.llm_state.player_buzzed_in(contestant)
