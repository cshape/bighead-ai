from enum import Enum, auto
from typing import Dict, Any, List, Optional
import logging
from pydantic import BaseModel
import json

logger = logging.getLogger(__name__)

class LLMGameState(str, Enum):
    """Game states specific to AI player interaction."""
    QUESTION_DISPLAYED = "QUESTION_DISPLAYED"
    PLAYER_BUZZED_IN = "PLAYER_BUZZED_IN"
    AWAITING_ANSWER = "AWAITING_ANSWER"
    SELECTING_QUESTION = "SELECTING_QUESTION"
    MAKING_WAGER = "MAKING_WAGER"
    GAME_OVER = "GAME_OVER"

class AIPlayerState(BaseModel):
    """State information for an AI player."""
    name: str
    state: LLMGameState = LLMGameState.GAME_OVER
    category: Optional[str] = None
    question_text: Optional[str] = None
    value: Optional[int] = None
    player_score: int = 0
    wager_type: Optional[str] = None
    max_wager: Optional[int] = None
    available_categories: List[str] = []
    available_values: List[int] = []
    buzzing_player: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to a dictionary for LLM input."""
        return {
            "state": self.state,
            "category": self.category,
            "question_text": self.question_text,
            "value": self.value,
            "player_score": self.player_score,
            "wager_type": self.wager_type,
            "max_wager": self.max_wager,
            "available_categories": self.available_categories,
            "available_values": self.available_values,
            "buzzing_player": self.buzzing_player
        }

class LLMStateManager:
    """
    Manages the state of AI players for LLM integration.
    This class maps game events to LLM states and maintains context
    for each AI player in the game.
    """

    def __init__(self, game_id: Optional[str] = None):
        """Initialize the state manager.

        Args:
            game_id: Optional game ID for debugging/logging purposes
        """
        self.game_id = game_id
        self.player_states: Dict[str, AIPlayerState] = {}
        self.available_categories: List[str] = []
        self.available_values: List[int] = [200, 400, 600, 800, 1000]
        logger.info(f"LLM State Manager initialized{f' for game {game_id}' if game_id else ''}")
    
    def register_ai_player(self, name: str) -> None:
        """Register a new AI player."""
        if name in self.player_states:
            logger.warning(f"AI player {name} already registered")
            return
        
        self.player_states[name] = AIPlayerState(name=name)
        logger.info(f"AI player {name} registered with state manager")
    
    def update_categories(self, categories: List[str]) -> None:
        """Update available categories."""
        self.available_categories = categories
        logger.info(f"Updated available categories: {categories}")
        
        # Update for all AI players
        for player_state in self.player_states.values():
            player_state.available_categories = categories
    
    def question_displayed(self, category: str, value: int, question_text: str) -> None:
        """
        Update state when a question is displayed.
        
        Args:
            category: The category of the question
            value: The dollar value of the question
            question_text: The text of the question
        """
        logger.info(f"Question displayed: {category}, ${value}, '{question_text}'")
        
        for name, player_state in self.player_states.items():
            player_state.state = LLMGameState.QUESTION_DISPLAYED
            player_state.category = category
            player_state.value = value
            player_state.question_text = question_text
            player_state.buzzing_player = None
            logger.debug(f"Updated AI player {name} for question displayed")
    
    def player_buzzed_in(self, player_name: str) -> None:
        """
        Update state when a player buzzes in.
        
        Args:
            player_name: The name of the player who buzzed in
        """
        logger.info(f"Player buzzed in: {player_name}")
        
        for name, player_state in self.player_states.items():
            player_state.state = LLMGameState.PLAYER_BUZZED_IN
            player_state.buzzing_player = player_name
            
            # If this AI player buzzed in, they should prepare to answer
            if name == player_name:
                player_state.state = LLMGameState.AWAITING_ANSWER
                logger.debug(f"AI player {name} is now awaiting answer")
    
    def selecting_question(self, player_name: str) -> None:
        """
        Update state when a player needs to select a question.
        
        Args:
            player_name: The name of the player who needs to select
        """
        logger.info(f"Player {player_name} is selecting a question")
        
        for name, player_state in self.player_states.items():
            # Only the player whose turn it is should be in SELECTING_QUESTION state
            if name == player_name:
                player_state.state = LLMGameState.SELECTING_QUESTION
                logger.debug(f"AI player {name} is now selecting a question")
            else:
                player_state.state = LLMGameState.GAME_OVER
    
    def making_wager(self, player_name: str, wager_type: str, max_wager: int) -> None:
        """
        Update state when a player needs to make a wager.
        
        Args:
            player_name: The name of the player making the wager
            wager_type: The type of wager (Daily Double or Final Jeopardy)
            max_wager: The maximum allowed wager amount
        """
        logger.info(f"Player {player_name} is making a {wager_type} wager (max: ${max_wager})")
        
        for name, player_state in self.player_states.items():
            # Only the player who needs to make a wager should be in MAKING_WAGER state
            if name == player_name:
                player_state.state = LLMGameState.MAKING_WAGER
                player_state.wager_type = wager_type
                player_state.max_wager = max_wager
                logger.debug(f"AI player {name} is now making a wager")
    
    def update_player_score(self, player_name: str, score: int) -> None:
        """
        Update a player's score.
        
        Args:
            player_name: The name of the player
            score: The player's new score
        """
        if player_name in self.player_states:
            self.player_states[player_name].player_score = score
            logger.debug(f"Updated AI player {player_name} score to ${score}")
    
    def question_dismissed(self) -> None:
        """Update state when a question is dismissed."""
        logger.info("Question dismissed")
        
        for player_state in self.player_states.values():
            # Reset to default game state
            player_state.state = LLMGameState.GAME_OVER
            player_state.category = None
            player_state.question_text = None
            player_state.value = None
            player_state.buzzing_player = None
    
    def get_player_state(self, player_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the current state for an AI player.
        
        Args:
            player_name: The name of the AI player
            
        Returns:
            Dictionary of the player's state or None if player not found
        """
        if player_name not in self.player_states:
            logger.warning(f"AI player {player_name} not found in state manager")
            return None
        
        return self.player_states[player_name].to_dict() 