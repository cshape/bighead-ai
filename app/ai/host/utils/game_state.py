"""
Game state tracking for the AI host
"""

import logging
import time
from typing import Dict, List, Set, Any, Optional
from collections import deque, defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class Question:
    """Represents a Big Head question"""
    text: str
    answer: str
    category: str
    value: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "text": self.text,
            "answer": self.answer,
            "category": self.category,
            "value": self.value
        }

@dataclass
class GameState:
    """Tracks the current state of the game"""
    # Game setup state
    welcome_completed: bool = False
    gathering_preferences: bool = False
    waiting_for_preferences: bool = False
    preference_collection_start_time: float = 0
    preference_countdown_started: bool = False
    preference_countdown_time: float = 0
    game_started: bool = False
    board_generation_started: bool = False
    expected_player_count: int = 3
    
    # Player state
    player_names: Set[str] = field(default_factory=set)
    player_with_control: Optional[str] = None
    buzzed_player: Optional[str] = None
    
    # Question state
    current_question: Optional[Dict[str, Any]] = None
    incorrect_attempts: Set[str] = field(default_factory=set)
    read_questions: Set[str] = field(default_factory=set)
    
    # Chat history for preferences
    recent_chat_messages: List[Dict[str, Any]] = field(default_factory=list)
    chat_history: deque = field(default_factory=lambda: deque(maxlen=200))
    
    # Board state  
    categories: List[str] = field(default_factory=list)
    board_generated: bool = False
    
    # Track player selection patterns
    category_selections: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    def reset(self):
        """Reset the game state for a new game"""
        # Keep player names and chat history, reset everything else
        self.welcome_completed = False
        self.gathering_preferences = False
        self.waiting_for_preferences = False
        self.preference_collection_start_time = 0
        self.preference_countdown_started = False
        self.preference_countdown_time = 0
        self.game_started = False
        
        self.player_with_control = None
        self.buzzed_player = None
        
        self.current_question = None
        self.incorrect_attempts = set()
        self.read_questions = set()
        
        self.recent_chat_messages = []
        
        self.categories = []
        self.board_generated = False
        
        # Reset selection patterns
        self.category_selections = defaultdict(int)
    
    # Getter/setter methods for cleaner API access
    
    def is_game_started(self) -> bool:
        """Check if the game has been started"""
        return self.game_started
    
    def set_game_started(self, value: bool):
        """Set whether the game has been started"""
        self.game_started = value
    
    def is_welcome_completed(self) -> bool:
        """Check if the welcome message has been completed"""
        return self.welcome_completed
    
    def set_welcome_completed(self, value: bool):
        """Set whether the welcome message has been completed"""
        self.welcome_completed = value
    
    def is_waiting_for_preferences(self) -> bool:
        """Check if the game is waiting for player preferences"""
        return self.waiting_for_preferences
    
    def set_waiting_for_preferences(self, value: bool):
        """Set whether the game is waiting for player preferences"""
        self.waiting_for_preferences = value
    
    def is_gathering_preferences(self) -> bool:
        """Check if gathering preferences is active"""
        return self.gathering_preferences
    
    def get_player_names(self) -> List[str]:
        """Get a list of player names"""
        return list(self.player_names)
    
    def add_player(self, player_name: str):
        """Add a player to the game state"""
        self.player_names.add(player_name)
    
    def get_player_with_control(self) -> Optional[str]:
        """Get the player with control of the board"""
        return self.player_with_control
    
    def set_player_with_control(self, player_name: str, used_questions: Set[str]):
        """Set the player with control of the board"""
        self.player_with_control = player_name
    
    def set_buzzed_player(self, player_name: str, incorrect_attempts: Set[str]):
        """Set the player who has buzzed in"""
        self.buzzed_player = player_name
    
    def reset_buzzed_player(self):
        """Reset the buzzed player"""
        self.buzzed_player = None
    
    def track_incorrect_attempt(self, player_name: str):
        """Track an incorrect answer attempt"""
        self.incorrect_attempts.add(player_name)
    
    def set_question(self, text: str, answer: str, category: str, value: int):
        """Set the current question"""
        self.current_question = {
            "text": text,
            "answer": answer,
            "category": category,
            "value": value
        }
    
    def has_question_been_read(self, question_text: str) -> bool:
        """Check if a question has been read already"""
        return question_text in self.read_questions
    
    def mark_question_read(self, question_text: str):
        """Mark a question as having been read"""
        self.read_questions.add(question_text)
    
    def reset_question(self):
        """Reset the current question"""
        self.current_question = None
        self.incorrect_attempts = set()
    
    def record_category_selection(self, player: str, category: str):
        """Record a player's category selection"""
        if not player or not category:
            return
            
        # Track which categories a player selects
        key = f"{player}:{category}"
        self.category_selections[key] += 1
        
    def get_player_preferred_categories(self, player: str) -> List[str]:
        """
        Get a player's most frequently selected categories
        
        Args:
            player: The player name
            
        Returns:
            List of categories sorted by selection frequency
        """
        # Extract all selections for this player
        selections = {}
        for key, count in self.category_selections.items():
            if key.startswith(f"{player}:"):
                category = key.split(":", 1)[1]
                selections[category] = count
                
        # Sort by frequency (descending)
        sorted_categories = sorted(selections.items(), key=lambda x: x[1], reverse=True)
        return [category for category, _ in sorted_categories]