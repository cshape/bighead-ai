import json
import os
import logging
from typing import Dict, Any, List, Optional
from ..models.board import Board
from ..models.category import Category
from ..models.contestant import Contestant
from ..models.question import Question, Clue, Answer
from ..models.finalbighead import FinalBigHeadClue, FinalBigHeadState

logger = logging.getLogger(__name__)

class BoardFactory:
    def __init__(self, filename: str = "questions", game_data_path: str = "game_data/"):
        self.filename = filename
        self.game_data_path = game_data_path
        logger.info(f"BoardFactory initialized with path: {game_data_path}")
    
    def initialize(self) -> Board:
        """Initialize with default board (backward compatibility)"""
        return self.load_board(self.filename)
    
    def load_board(self, filename: str) -> Board:
        """Load a specific board by filename"""
        logger.info(f"Loading board from filename: {filename}")
        
        # Try the specified filename first
        spec_path = os.path.join(self.game_data_path, f"{filename}.json")
        app_path = os.path.join("app", self.game_data_path, f"{filename}.json")
        
        # Check both possible locations
        for path in [spec_path, app_path]:
            if os.path.exists(path):
                logger.info(f"Found game data at: {path}")
                with open(path, 'r') as f:
                    data = json.load(f)
                
                # Check if the data has all required sections
                if self._validate_data(data, path):
                    board = self.from_json(data)
                    logger.info(f"Successfully loaded board with {len(board.categories)} categories")
                    return board
        
        raise FileNotFoundError(f"Could not find a valid game data file for {filename}")
    
    def _validate_data(self, data: Dict[str, Any], path: str) -> bool:
        """Validate that the game data has all required sections."""
        required_keys = ["contestants", "categories", "final"]
        missing_keys = [k for k in required_keys if k not in data]
        
        if missing_keys:
            logger.error(f"Game data file {path} is missing required sections: {missing_keys}")
            return False
            
        # Check if categories is empty
        if not data["categories"]:
            logger.error(f"Game data file {path} has empty categories list")
            return False
            
        return True
    
    def from_json(self, data: Dict[str, Any]) -> Board:
        # Create contestants
        contestants = [
            Contestant(name=c["name"], score=c.get("score", 0))
            for c in data["contestants"]
        ]
        logger.info(f"Created {len(contestants)} contestants")
        
        # Create categories with questions
        categories = []
        for category_data in data["categories"]:
            questions = []
            for q in category_data["questions"]:
                question = Question(
                    clue=Clue(text=q["clue"]),
                    answer=Answer(text=q["answer"]),
                    value=q["value"],
                    double_big_head=q.get("double_big_head", False),
                    type=q.get("type", "text"),
                    used=q.get("used", False)
                )
                questions.append(question)
            
            category = Category(name=category_data["name"], questions=questions)
            categories.append(category)
            logger.info(f"Created category '{category_data['name']}' with {len(questions)} questions")
        
        # Create final big head
        if "final" not in data:
            logger.error("Final Big Head is not defined in your questions file")
            raise ValueError("Final Big Head is not defined in your questions file")
        
        final = data["final"]
        final_big_head_clue = FinalBigHeadClue(
            category=final["category"],
            clue=final["clue"],
            answer=final["answer"]
        )
        logger.info(f"Created Final Big Head with category: {final['category']}")
        
        final_big_head_state = FinalBigHeadState(
            clue=final_big_head_clue,
            contestants=[c.name for c in contestants]
        )
        
        # Create board
        board = Board(
            contestants=contestants,
            categories=categories,
            final_big_head_state=final_big_head_state
        )
        
        return board 