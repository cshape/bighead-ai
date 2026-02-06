"""
Game state management for the AI host
"""

import logging
import time
from typing import List, Dict, Set, Optional, Any
from .utils.game_state import GameState

logger = logging.getLogger(__name__)

class GameStateManager:
    """Manages the game state tracking for the AI host"""
    
    def __init__(self):
        """Initialize the game state manager"""
        self.game_state = GameState()
        # Set the expected player count to 3 to trigger welcome once all players have joined
        self.game_state.expected_player_count = 3

        # Last-known buzzer state (used for change detection in game_flow_manager)
        self.buzzer_active = False

        # Track when buzzer was activated to calculate timeout properly
        self.buzzer_activation_time = None
        
        # Add a cooldown mechanism to prevent duplicate question detection
        self.last_question_time = 0
        self.question_cooldown = 5  # 5 seconds cooldown
        
        # Track the last processed answer message to avoid reprocessing as clue selection
        self.last_processed_answer_key = None
        
        # Track recently answered questions to prevent them from reappearing
        self.last_answered_question = None
        self.answer_cooldown_time = 0
        self.answer_cooldown = 3  # seconds
        
        # Store recent chat messages for preferences
        self.recent_chat_messages = []  # Store recent chat messages for preferences
        self.max_preference_messages = 20  # Maximum number of messages to use for preferences
        
        # Mark when we've started gathering preferences, to avoid using
        # messages after board generation has started
        self.gathering_preferences = True
        
        # Track buzzer state - which players have given incorrect answers
        self.incorrect_attempts = set()
        
        self.player_names = set()
        self.player_preferences = {}  # Direct storage for preferences from registration
    
    def is_game_started(self) -> bool:
        """Check if the game has been started"""
        return self.game_state.is_game_started()
    
    def set_game_started(self, value: bool):
        """Set whether the game has been started"""
        self.game_state.set_game_started(value)
    
    def is_welcome_completed(self) -> bool:
        """Check if the welcome message has been completed"""
        return self.game_state.is_welcome_completed()
    
    def set_welcome_completed(self, value: bool):
        """Set whether the welcome message has been completed"""
        self.game_state.set_welcome_completed(value)
    
    def is_waiting_for_preferences(self) -> bool:
        """Check if the game is waiting for player preferences"""
        return self.game_state.is_waiting_for_preferences()
    
    def set_waiting_for_preferences(self, value: bool):
        """Set whether the game is waiting for player preferences"""
        self.game_state.set_waiting_for_preferences(value)
    
    def is_gathering_preferences(self) -> bool:
        """Check if we are gathering preferences from chat"""
        return self.game_state.is_gathering_preferences()
    
    def get_player_names(self) -> List[str]:
        """Get a list of player names"""
        return self.game_state.get_player_names()
    
    def add_player(self, player_name: str):
        """Add a player to the game state"""
        self.game_state.add_player(player_name)
    
    def get_player_with_control(self) -> Optional[str]:
        """Get the player with control of the board"""
        return self.game_state.get_player_with_control()
    
    def set_player_with_control(self, player_name: str, used_questions: Set[str]):
        """Set the player with control of the board"""
        self.game_state.set_player_with_control(player_name, used_questions)
    
    def get_buzzed_player(self) -> Optional[str]:
        """Get the player who has buzzed in"""
        return self.game_state.buzzed_player
    
    def set_buzzed_player(self, player_name: str, incorrect_attempts: Set[str]):
        """Set the player who has buzzed in"""
        self.game_state.set_buzzed_player(player_name, incorrect_attempts)
    
    def reset_buzzed_player(self):
        """Reset the buzzed player"""
        self.game_state.reset_buzzed_player()
    
    def track_incorrect_attempt(self, player_name: str):
        """Track an incorrect answer attempt"""
        self.game_state.track_incorrect_attempt(player_name)
        self.incorrect_attempts.add(player_name)
    
    def clear_incorrect_attempts(self):
        """Clear the incorrect answer attempts tracking"""
        self.incorrect_attempts.clear()
        
    def get_incorrect_attempts(self) -> Set[str]:
        """Get the set of players who have given incorrect answers"""
        return self.incorrect_attempts
    
    def should_check_for_clue_selection(self) -> bool:
        """Check if we should be checking for clue selection messages"""
        return self.game_state.get_player_with_control() is not None and not self.game_state.current_question
    
    def set_question(self, text: str, answer: str, category: str, value: int):
        """Set the current question"""
        self.game_state.set_question(text, answer, category, value)
        # Clear incorrect attempts when setting a new question
        self.clear_incorrect_attempts()
    
    def has_question_been_read(self, question_text: str) -> bool:
        """Check if a question has been read already"""
        return self.game_state.has_question_been_read(question_text)
    
    def mark_question_read(self, question_text: str):
        """Mark a question as having been read"""
        self.game_state.mark_question_read(question_text)
    
    def reset_question(self):
        """Reset the current question"""
        self.game_state.reset_question()
        # Clear incorrect attempts when resetting a question
        self.clear_incorrect_attempts()
    
    def add_chat_message(self, username: str, message: str):
        """Store a chat message for preference collection"""
        if len(message) <= 3:
            return  # Still filter out very short messages
            
        self.recent_chat_messages.append({
            "username": username,
            "message": message
        })
        
        # Keep only the most recent messages
        if len(self.recent_chat_messages) > self.max_preference_messages:
            self.recent_chat_messages.pop(0)
        
        logger.info(f"Stored chat message for preferences: {username}: {message}")
        
    def add_player_preference(self, username: str, preference: str):
        """Store a player's preferences from registration directly"""
        if not preference.strip():
            return
            
        self.player_preferences[username] = preference.strip()
        logger.info(f"Stored preference from registration: {username}: {preference}")
        
    def get_preference_messages(self) -> List[Dict[str, str]]:
        """Get the stored preference messages, including those from registration"""
        # Combine registration preferences with chat messages
        all_preferences = list(self.recent_chat_messages)
        
        # Add preferences from registration
        for username, preference in self.player_preferences.items():
            all_preferences.append({
                "username": username,
                "message": preference
            })
            
        logger.info(f"Combined preferences: {len(all_preferences)} total ({len(self.player_preferences)} from registration)")
        return all_preferences 