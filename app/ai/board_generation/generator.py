"""
Board Generator module for creating Big Head game data using LLM calls.
"""

import os
import json
import random
import logging
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime

from app.ai.utils.llm import LLMClient, LLMConfig

logger = logging.getLogger(__name__)

class BoardGenerator:
    """
    Generates Big Head game boards with categories and questions using LLM.
    """

    def __init__(self, output_dir: str = "app/game_data", model: str = "gpt-4.1", user_input: str = ""):
        """
        Initialize the board generator.
        
        Args:
            output_dir: Directory where generated boards will be saved
            model: LLM model to use for generation
            user_input: User preferences or requests for the game content
        """
        self.output_dir = output_dir
        self.user_input = user_input
        self.llm_client = LLMClient(
            config=LLMConfig(
                model=model,
                temperature=0.7,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
        )
        os.makedirs(output_dir, exist_ok=True)
        
    async def generate_categories(self) -> List[str]:
        """
        Generate 5 diverse Big Head category names.
        
        Returns:
            List of 5 category names
        """
        result = await self.llm_client.chat_with_template(
            user_template="board_category_generation_prompt.j2",
            user_context={"user_input": self.user_input},
            system_template="board_category_generation.j2",
        )
        
        try:
            response_obj = json.loads(result)
            if not isinstance(response_obj, dict) or "categories" not in response_obj:
                logger.warning("LLM response missing 'categories' attribute, using default")
                return ["History", "Science", "Literature", "Geography", "Pop Culture"]
                
            categories = response_obj["categories"]
            if not isinstance(categories, list) or len(categories) != 5:
                logger.warning("LLM didn't return 5 categories, using default")
                return ["History", "Science", "Literature", "Geography", "Pop Culture"]
            return categories
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response as JSON: {result}")
            return ["History", "Science", "Literature", "Geography", "Pop Culture"]
    
    async def generate_questions_for_category(self, category: str) -> Dict[str, Any]:
        """
        Generate 5 questions of increasing difficulty for a category.
        
        Args:
            category: The category name
        
        Returns:
            Dict with category object containing questions
        """
        result = await self.llm_client.chat_with_template(
            user_template="board_question_generation_prompt.j2",
            user_context={"category": category, "user_input": self.user_input},
            system_template="board_question_generation.j2",
        )
        
        try:
            response_obj = json.loads(result)
            if not isinstance(response_obj, dict) or "category_data" not in response_obj:
                logger.warning(f"LLM response missing 'category_data' attribute for {category}")
                return self._create_fallback_category(category)
                
            category_data = response_obj["category_data"]
            if "name" not in category_data or "questions" not in category_data:
                logger.warning(f"LLM didn't return proper category structure for {category}")
                return self._create_fallback_category(category)
                
            # Validate questions
            questions = category_data["questions"]
            if len(questions) != 5:
                logger.warning(f"LLM didn't return 5 questions for {category}")
                questions = questions[:5] if len(questions) > 5 else questions
                while len(questions) < 5:
                    questions.append({
                        "clue": f"Placeholder clue for {category}",
                        "answer": "Placeholder answer",
                        "value": 200 * (len(questions) + 1),
                        "double_big_head": False,
                        "type": "text"
                    })
                category_data["questions"] = questions
                
            # Ensure values are correct
            values = [200, 400, 600, 800, 1000]
            for i, question in enumerate(questions):
                question["value"] = values[i]
                question["double_big_head"] = False
                
            return category_data
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response as JSON for {category}: {result}")
            return self._create_fallback_category(category)
    
    def _create_fallback_category(self, category: str) -> Dict[str, Any]:
        """Create a fallback category if LLM generation fails."""
        return {
            "name": category,
            "questions": [
                {
                    "clue": f"Easy clue about {category}",
                    "answer": f"Answer about {category}",
                    "value": 200,
                    "double_big_head": False,
                    "type": "text"
                },
                {
                    "clue": f"Somewhat harder clue about {category}",
                    "answer": f"Answer about {category}",
                    "value": 400,
                    "double_big_head": False,
                    "type": "text"
                },
                {
                    "clue": f"Medium difficulty clue about {category}",
                    "answer": f"Answer about {category}",
                    "value": 600,
                    "double_big_head": False,
                    "type": "text"
                },
                {
                    "clue": f"Challenging clue about {category}",
                    "answer": f"Answer about {category}",
                    "value": 800,
                    "double_big_head": False,
                    "type": "text"
                },
                {
                    "clue": f"Very difficult clue about {category}",
                    "answer": f"Answer about {category}",
                    "value": 1000,
                    "double_big_head": False,
                    "type": "text"
                }
            ]
        }
    
    async def generate_board(self, board_name: Optional[str] = None, add_double_big_heads: bool = True) -> Dict[str, Any]:
        """
        Generate a complete Big Head board with 5 categories and 25 questions.
        
        Args:
            board_name: Optional name for the board file
            add_double_big_heads: Whether to add daily doubles (1-2 random questions)
        
        Returns:
            Complete board data as a dictionary
        """
        # Generate categories
        categories = await self.generate_categories()
        logger.info(f"Generated categories: {categories}")
        
        # Generate questions for each category concurrently
        category_tasks = []
        for category in categories:
            task = self.generate_questions_for_category(category)
            category_tasks.append(task)
        
        # Wait for all categories to be generated
        category_data = await asyncio.gather(*category_tasks)
        
        # Add daily doubles if requested
        if add_double_big_heads:
            # Add 1-2 daily doubles, excluding $200 questions
            double_big_head_count = random.randint(1, 2)
            excludes = []
            for _ in range(double_big_head_count):
                while True:
                    cat_idx = random.randint(0, 4)
                    q_idx = random.randint(1, 4)  # Skip $200 questions
                    if (cat_idx, q_idx) not in excludes:
                        category_data[cat_idx]["questions"][q_idx]["double_big_head"] = True
                        excludes.append((cat_idx, q_idx))
                        break
        
        # Generate Final Big Head
        final_big_head = await self._generate_final_big_head()
        
        # Create the full board data
        if not board_name:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            board_name = f"generated_{timestamp}"
            
        board_data = {
            "contestants": [
                {"name": "Player 1", "score": 0},
                {"name": "Player 2", "score": 0},
                {"name": "Player 3", "score": 0}
            ],
            "categories": category_data,
            "final": final_big_head
        }
        
        return board_data
    
    async def _generate_final_big_head(self) -> Dict[str, str]:
        """
        Generate a Final Big Head category, clue, and answer.
        
        Returns:
            Dictionary with final Big Head data
        """
        result = await self.llm_client.chat_with_template(
            user_template="board_final_big_head_prompt.j2",
            user_context={"user_input": self.user_input},
            system_template="board_final_big_head.j2",
        )
        
        try:
            response_obj = json.loads(result)
            if not isinstance(response_obj, dict) or "final_big_head" not in response_obj:
                logger.warning("LLM response missing 'final_big_head' attribute")
                return {
                    "category": "Final Big Head",
                    "clue": "This is a placeholder for the final Big Head clue",
                    "answer": "Placeholder answer"
                }
                
            final = response_obj["final_big_head"]
            required_keys = ["category", "clue", "answer"]
            if not all(key in final for key in required_keys):
                logger.warning("LLM didn't return proper Final Big Head structure")
                return {
                    "category": "Final Big Head",
                    "clue": "This is a placeholder for the final Big Head clue",
                    "answer": "Placeholder answer"
                }
                
            return final
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response as JSON for Final Big Head: {result}")
            return {
                "category": "Final Big Head",
                "clue": "This is a placeholder for the final Big Head clue",
                "answer": "Placeholder answer"
            }
    
    async def generate_and_save_board(self, board_name: Optional[str] = None, add_double_big_heads: bool = True, user_input: Optional[str] = None) -> str:
        """
        Generate a board and save it to a JSON file.
        
        Args:
            board_name: Optional name for the board file
            add_double_big_heads: Whether to add daily doubles
            user_input: Optional user preferences (overwrites the object's user_input if provided)
            
        Returns:
            Path to the saved JSON file
        """
        # Update user input if provided
        original_user_input = self.user_input
        if user_input is not None:
            self.user_input = user_input
            
        try:
            # Generate categories first
            categories = await self.generate_categories()
            logger.info(f"Generated categories: {categories}")
            
            if not board_name:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                board_name = f"generated_{timestamp}"
            
            # Create placeholder board data
            board_data = {
                "contestants": [
                    {"name": "Player 1", "score": 0},
                    {"name": "Player 2", "score": 0},
                    {"name": "Player 3", "score": 0}
                ],
                "categories": [],
                "final": None
            }
            
            # Save initial board with placeholders
            file_path = os.path.join(self.output_dir, f"{board_name}.json")
            with open(file_path, 'w') as f:
                json.dump(board_data, f, indent=2)
            
            # Generate questions for each category concurrently
            category_tasks = []
            for category in categories:
                task = self.generate_questions_for_category(category)
                category_tasks.append(task)
            
            # Wait for all categories to be generated
            category_data = await asyncio.gather(*category_tasks)
            
            # Add daily doubles if requested
            if add_double_big_heads:
                # Add 1-2 daily doubles, excluding $200 questions
                double_big_head_count = random.randint(1, 2)
                excludes = []
                for _ in range(double_big_head_count):
                    while True:
                        cat_idx = random.randint(0, 4)
                        q_idx = random.randint(1, 4)  # Skip $200 questions
                        if (cat_idx, q_idx) not in excludes:
                            category_data[cat_idx]["questions"][q_idx]["double_big_head"] = True
                            excludes.append((cat_idx, q_idx))
                            break
            
            # Generate Final Big Head
            final_big_head = await self._generate_final_big_head()
            
            # Update board data with all categories and final big head
            board_data["categories"] = category_data
            board_data["final"] = final_big_head
            
            # Save complete board data
            with open(file_path, 'w') as f:
                json.dump(board_data, f, indent=2)
            
            logger.info(f"Board saved to {file_path}")
            return file_path
        finally:
            # Restore original user input
            if user_input is not None:
                self.user_input = original_user_input 