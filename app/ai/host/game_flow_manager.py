"""
Game Flow Manager for handling game progression and state monitoring.
"""

import logging
import asyncio
import time
from typing import Optional

logger = logging.getLogger(__name__)

class GameFlowManager:
    """
    Manages the game flow, state monitoring, and game progression.
    """
    
    def __init__(self):
        """Initialize the game flow manager."""
        # Dependencies (to be set later)
        self.game_service = None
        self.game_state_manager = None
        self.chat_processor = None
        self.audio_manager = None
        self.buzzer_manager = None
        self.board_manager = None
        self.game_instance = None  # Will be set by service.py
    
    def set_dependencies(self, game_service=None, game_state_manager=None, 
                         chat_processor=None, audio_manager=None, 
                         buzzer_manager=None, board_manager=None):
        """Set dependencies required for game flow management."""
        if game_service:
            self.game_service = game_service
        if game_state_manager:
            self.game_state_manager = game_state_manager
        if chat_processor:
            self.chat_processor = chat_processor
        if audio_manager:
            self.audio_manager = audio_manager
        if buzzer_manager:
            self.buzzer_manager = buzzer_manager
        if board_manager:
            self.board_manager = board_manager

    def _get_game_id(self) -> Optional[str]:
        """Get the game_id from game_instance if available."""
        return self.game_instance.game_id if self.game_instance else None

    async def monitor_game_state(self):
        """Monitor the game state and respond to changes."""
        try:
            # Skip if game service is not available yet
            if not self.game_service:
                # If no game service, make sure timer is cancelled
                if self.buzzer_manager:
                    self.buzzer_manager.cancel_timeout()
                return

            # Handle different game states based on what's currently happening
            
            # Check if we're in the waiting/lobby stage 
            if not self.game_state_manager.is_game_started():
                # Cancel any timer if we're in lobby
                if self.buzzer_manager:
                    self.buzzer_manager.cancel_timeout()
                await self.check_game_start_conditions()
                return
                
            # Check if there's a current question
            current_question = None
            if self.game_instance and self.game_instance.current_question:
                current_question = self.game_instance.current_question

            if current_question and not self.game_state_manager.game_state.current_question:
                # We have a new question to process
                # Cancel any existing timer when a new question appears
                if self.buzzer_manager:
                    self.buzzer_manager.cancel_timeout()
                
                question_data = current_question
                
                # Create a question object for our state
                self.game_state_manager.set_question(
                    text=question_data["text"],
                    answer=question_data["answer"],
                    category=question_data["category"],
                    value=question_data["value"]
                )
                
                logger.debug(f"New question detected: {question_data['text'][:30]}...")
                
                # Read the question if it hasn't been read yet
                if not self.game_state_manager.has_question_been_read(question_data["text"]):
                    speech_text = f"For {question_data['category']}, ${question_data['value']}. {question_data['text']}"
                    logger.debug(f"Synthesizing speech: {speech_text}")
                    
                    await self.audio_manager.synthesize_and_play_speech(speech_text, is_question_audio=True)
                    self.game_state_manager.mark_question_read(question_data["text"])
                
            # Check if we need to handle a player's answer - improved to detect new buzzer events
            current_buzzer = self.game_instance.last_buzzer if self.game_instance else None
            buzzed_player = self.game_state_manager.get_buzzed_player()
            
            # Detect if a new player has buzzed in
            if (current_buzzer and 
                (not buzzed_player or current_buzzer != self.buzzer_manager.last_buzzer)):
                
                player_name = current_buzzer
                logger.debug(f"Player buzzed in: {player_name}")
                
                # Update our tracking
                self.buzzer_manager.last_buzzer = player_name
                
                # Update our state
                self.game_state_manager.set_buzzed_player(player_name, set())
                
                # Let players know they're being evaluated
                await self.chat_processor.send_chat_message(f"Let me evaluate {player_name}'s answer...")
                
                # Cancel any active buzzer timeout when someone buzzes in
                if self.buzzer_manager:
                    self.buzzer_manager.cancel_timeout()
            
            # Check if the buzzer state has changed - detect buzzer activation
            buzzer_active = self.game_instance.buzzer_active if self.game_instance else False
            if buzzer_active and not self.game_state_manager.buzzer_active:
                logger.debug("Buzzer has been activated")
                self.game_state_manager.buzzer_active = True
                asyncio.create_task(self.buzzer_manager.activate_buzzer(game_id=self._get_game_id()))
            elif not buzzer_active and self.game_state_manager.buzzer_active:
                logger.debug("Buzzer has been deactivated")
                self.game_state_manager.buzzer_active = False
                asyncio.create_task(self.buzzer_manager.deactivate_buzzer(game_id=self._get_game_id()))
                
            # Check if the question has been dismissed
            current_question_check = None
            if self.game_instance and self.game_instance.current_question:
                current_question_check = self.game_instance.current_question

            if not current_question_check and self.game_state_manager.game_state.current_question:
                # Question has been dismissed, reset our state
                logger.debug("Question was dismissed, resetting state")
                self.game_state_manager.reset_question()
                self.buzzer_manager.last_buzzer = None
                asyncio.create_task(self.buzzer_manager.deactivate_buzzer(game_id=self._get_game_id()))
                self.game_state_manager.buzzer_active = False
                
                # Cancel any buzzer timeout if question was dismissed
                if self.buzzer_manager:
                    self.buzzer_manager.cancel_timeout()
                
            # Check for clue selection if there's no active question
            if not self.game_state_manager.game_state.current_question and not current_question_check:
                # No question active, make sure timer is cancelled
                if self.buzzer_manager:
                    self.buzzer_manager.cancel_timeout()
                await self.check_for_clue_selection()
                
        except Exception as e:
            logger.error(f"Error monitoring game state: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def check_game_start_conditions(self):
        """Check if all conditions are met to start the game."""
        try:
            # Log state at the beginning for debugging
            logger.debug(f"[GameStartCheck] game_started={self.game_state_manager.is_game_started()}, " +
                       f"welcome_completed={self.game_state_manager.is_welcome_completed()}, " +
                       f"waiting_for_prefs={self.game_state_manager.is_waiting_for_preferences()}, " +
                       f"countdown_started={self.game_state_manager.game_state.preference_countdown_started}")
            
            # Skip if the game is already started
            if self.game_state_manager.is_game_started():
                return
            
            # Skip if game service is not available
            if not self.game_service:
                logger.warning("Game service not available, cannot check game start conditions")
                return
                
            # Get current players - use game_instance state
            if not self.game_instance:
                logger.warning("No game_instance available in check_game_start_conditions")
                return
            state = self.game_instance.state
            current_players = list(state.contestants.values())
            current_player_count = len(current_players)
            
            # Update player names in game state
            for contestant in current_players:
                player_name = contestant.name
                if player_name and player_name not in self.game_state_manager.get_player_names():
                    self.game_state_manager.add_player(player_name)
                    # Welcome the player but don't ask for preferences
                    await self.chat_processor.send_chat_message(f"Welcome, {player_name}!")
            
            # If we have all players but haven't welcomed them yet
            if (current_player_count >= self.game_state_manager.game_state.expected_player_count and 
                not self.game_state_manager.is_welcome_completed()):
                logger.info("All players have joined. Welcoming...")
                await self.welcome_players()
                
                # Mark game as ready
                if self.game_service:
                    await self.game_service.connection_manager.broadcast_message(
                        "com.sc2ctl.jeopardy.game_ready",
                        {"ready": True},
                        game_id=self._get_game_id()
                    )
            
            # Check if we're waiting for preferences and should generate board
            if self.game_state_manager.is_waiting_for_preferences():
                current_time = time.time()
                countdown_remaining = 10 - (current_time - self.game_state_manager.game_state.preference_countdown_time) if self.game_state_manager.game_state.preference_countdown_started else 10
                logger.debug(f"Preference collection state: waiting={self.game_state_manager.is_waiting_for_preferences()}, " +
                           f"countdown_started={self.game_state_manager.game_state.preference_countdown_started}, " +
                           f"countdown_remaining={countdown_remaining:.1f}s")
                
                # If countdown is active and time is up, generate board
                if self.game_state_manager.game_state.preference_countdown_started and countdown_remaining <= 0:
                    logger.debug("Preference collection time up, generating board from preferences")
                    # Stop gathering preferences before generating board
                    self.game_state_manager.gathering_preferences = False
                    logger.debug(f"Stopped gathering preferences. Collected {len(self.game_state_manager.recent_chat_messages)} messages")
                    await self.generate_board_from_preferences()
                
        except Exception as e:
            logger.error(f"Error checking game start conditions: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
    async def welcome_players(self):
        """Welcome players to the game and announce the beginning."""
        try:
            # Get player names from game state
            player_names = self.game_state_manager.get_player_names()
            if not player_names:
                logger.warning("No players found in game state when trying to welcome")
                return
                
            # Don't reset chat message storage for preferences
            # We need to keep the registration preferences
            
            # Format player list for welcome message with proper grammar
            if len(player_names) == 3:
                player_list = f"{player_names[0]}, {player_names[1]}, and {player_names[2]}"
            else:
                player_list = ", ".join(player_names)  # Fallback for other counts
            
            # Welcome message without asking for preferences since we got them at registration
            welcome_message = f"Welcome to Jeopardy! Today's contestants are {player_list}. Let's get started!"
            logger.info(f"Sending welcome message: {welcome_message}")
            
            # Send welcome message
            await self.chat_processor.send_chat_message(welcome_message)
            if self.audio_manager:
                await self.audio_manager.synthesize_and_play_speech(welcome_message)
            
            # Mark welcome as completed
            self.game_state_manager.set_welcome_completed(True)
            
            # Skip the preference collection phase since we collected preferences during registration
            self.game_state_manager.set_waiting_for_preferences(False)
            
            # Directly generate the board
            logger.debug("Generating board from preferences collected during registration")
            await self.generate_board_from_preferences()
            
        except Exception as e:
            logger.error(f"Error in welcome players: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
    async def generate_board_from_preferences(self):
        """Generate a game board based on player preferences from chat."""
        try:
            # Log the count of messages before we stop gathering
            logger.debug(f"Before stopping gathering: {len(self.game_state_manager.recent_chat_messages)} chat messages collected")
            
            # Stop gathering new messages for preferences (in case this wasn't done earlier)
            self.game_state_manager.gathering_preferences = False
            
            # Get preference messages from the game state manager
            preference_messages = self.game_state_manager.get_preference_messages()
            logger.debug(f"Retrieved {len(preference_messages)} preference messages for board generation")
            
            # Force inclusion of user messages that might have been missed
            if len(preference_messages) == 0 and len(self.game_state_manager.recent_chat_messages) > 0:
                logger.debug("Preference messages collection failed - forcing use of recent_chat_messages")
                preference_messages = self.game_state_manager.recent_chat_messages
                logger.debug(f"Forced preference messages: {len(preference_messages)}")
            
            # Log a sample of the messages for debugging
            pref_summary = []
            for i, msg in enumerate(preference_messages[:3]):
                pref_text = f"{msg.get('username', 'Unknown')}: {msg.get('message', '')}"
                logger.debug(f"Preference message {i+1}: {pref_text}")
                pref_summary.append(pref_text)
            
            # Signal frontend to show placeholder board with question marks
            # Only do this if it's not already being shown (avoid duplicating)
            if self.game_service and not self.game_state_manager.game_state.board_generation_started:
                await self.game_service.connection_manager.broadcast_message(
                    "com.sc2ctl.jeopardy.start_board_generation",
                    {},
                    game_id=self._get_game_id()
                )
                self.game_state_manager.game_state.board_generation_started = True
            
            # Generate the board using the board manager
            board_name = await self.board_manager.generate_board_from_preferences(preference_messages)
            
            if board_name:
                # Mark game as ready to start
                self.game_state_manager.set_waiting_for_preferences(False)
                self.game_state_manager.set_game_started(True)
                
                # Announce the game is starting
                start_message = "The game board is ready! Let's play Jeopardy!"
                await self.chat_processor.send_chat_message(start_message)
                await self.audio_manager.synthesize_and_play_speech(start_message)
                
                # Start the game by assigning the first player control of the board
                await self.assign_first_player()
            else:
                # In case of error, try to start with a default board
                await self.board_manager.load_default_board()
                
                # Mark game as started even if we had an error
                self.game_state_manager.set_waiting_for_preferences(False)
                self.game_state_manager.set_game_started(True)
                
                # Notify players
                error_message = "I had trouble generating a custom board. Let's use a default board instead!"
                await self.chat_processor.send_chat_message(error_message)
                await self.audio_manager.synthesize_and_play_speech(error_message)
                
                # Start the game by assigning the first player control of the board
                await self.assign_first_player()
                
        except Exception as e:
            logger.error(f"Error generating board from preferences: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
    async def assign_first_player(self):
        """Assign the first player control of the board and prompt them to select the first clue."""
        try:
            # Get the first player from the game state
            player_names = self.game_state_manager.get_player_names()
            if not player_names:
                logger.warning("No players found when trying to assign first player")
                return
                
            first_player = player_names[0]
            logger.info(f"Assigning first player {first_player} control of the board")
            
            # Set the first player as having control of the board
            self.game_state_manager.set_player_with_control(first_player, set())
            
            # Notify game service to update frontend state
            if self.game_service:
                await self.game_service.connection_manager.broadcast_message(
                    "com.sc2ctl.jeopardy.select_question",
                    {"contestant": first_player},
                    game_id=self._get_game_id()
                )
            
            # Announce that the first player has control
            control_message = f"{first_player}, you have control of the board. Please select the first clue."
            await self.chat_processor.send_chat_message(control_message)
            await self.audio_manager.synthesize_and_play_speech(control_message)
            
        except Exception as e:
            logger.error(f"Error assigning first player: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
    async def check_for_clue_selection(self):
        """Check for clue selection messages from the player with control of the board."""
        # Only check if there's a player with control and no active question
        if not self.game_state_manager.should_check_for_clue_selection():
            return
            
        try:
            controlling_player = self.game_state_manager.get_player_with_control()
            if not controlling_player:
                return
                
            logger.debug(f"Player with control: {controlling_player} - waiting for clue selection")
            
            # For now, we'll just handle this in other ways (e.g., through chat events)
            
        except Exception as e:
            logger.error(f"Error checking for clue selection: {e}")
            import traceback
            logger.error(traceback.format_exc()) 