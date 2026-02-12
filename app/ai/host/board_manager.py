"""
Board generation and management for the AI host
"""

import logging
import json
import os
import time
import asyncio
import random
from typing import List, Dict, Any
from app.ai.board_generation.generator import BoardGenerator

logger = logging.getLogger(__name__)

class BoardManager:
    """Manages board generation and selection for the AI host"""

    def __init__(self):
        """Initialize the board manager"""
        self.game_service = None
        self.game_instance = None
    
    def set_game_service(self, game_service):
        """Set the game service reference"""
        self.game_service = game_service
        logger.info("Game service set for BoardManager")
    
    async def generate_board_from_preferences(self, preference_messages: List[Dict[str, str]]):
        """
        Generate a board based on user preferences.

        Args:
            preference_messages: List of messages containing user preferences
        """
        try:
            # TEST_MODE: load static questions.json board instead of generating via LLM
            if os.environ.get("TEST_MODE"):
                logger.info("TEST_MODE: Skipping LLM board generation, loading questions.json")
                if self.game_service and self.game_instance:
                    await self.game_service.select_board("questions", game_id=self.game_instance.game_id)

                    # Load questions.json to get categories for reveal animation
                    questions_path = os.path.join("app/game_data", "questions.json")
                    with open(questions_path, 'r') as f:
                        board_data = json.load(f)

                    # Reveal categories with short delay
                    for i, cat_data in enumerate(board_data.get("categories", [])):
                        await self.game_service.connection_manager.broadcast_message(
                            "com.sc2ctl.bighead.reveal_category",
                            {"index": i, "category": cat_data},
                            game_id=self.game_instance.game_id
                        )
                        await asyncio.sleep(0.2)

                    return "questions"
                else:
                    logger.error("TEST_MODE: Cannot select board - game_service or game_instance not set")
                    return None

            # Extract user preferences from messages
            user_preferences = " ".join([msg["message"] for msg in preference_messages])
            
            # Create board generator
            generator = BoardGenerator(user_input=user_preferences)
            
            # First, generate just the category names
            logger.info("Generating categories...")
            categories = await generator.generate_categories()
            logger.info(f"Generated categories: {categories}")
            
            # Generate a unique name for this game's board
            timestamp = time.strftime("%Y%m%d%H%M%S")
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
            file_path = os.path.join("app/game_data", f"{board_name}.json")
            with open(file_path, 'w') as f:
                json.dump(board_data, f, indent=2)
            
            # Start all category generation tasks concurrently
            category_tasks = []
            for category in categories:
                task = generator.generate_questions_for_category(category)
                category_tasks.append(task)
            
            # Wait for all categories to be generated
            category_data = await asyncio.gather(*category_tasks)
            
            # Reveal categories one by one with a small delay
            for i, cat_data in enumerate(category_data):
                logger.info(f"Revealing category {i+1} of {len(categories)}: {cat_data['name']}")
                if self.game_service:
                    game_id = self.game_instance.game_id if self.game_instance else None
                    await self.game_service.connection_manager.broadcast_message(
                        "com.sc2ctl.bighead.reveal_category",
                        {
                            "index": i,
                            "category": cat_data
                        },
                        game_id=game_id
                    )
                # Small delay between reveals for visual effect
                await asyncio.sleep(0.5)
            
            # Add daily doubles if requested
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
            
            # Generate the final object
            board_data["categories"] = category_data
            board_data["final"] = await generator._generate_final_big_head()
            
            # Save complete board data
            with open(file_path, 'w') as f:
                json.dump(board_data, f, indent=2)
            
            # Set the board in the game service
            if self.game_service and self.game_instance:
                await self.game_service.select_board(board_name, game_id=self.game_instance.game_id)
            elif not self.game_instance:
                logger.error("Cannot select board - game_instance not set on BoardManager")
            
            return board_name
            
        except Exception as e:
            logger.error(f"Error generating board: {e}")
            raise
    
    async def load_default_board(self):
        """Load the default board as a fallback"""
        try:
            logger.info("Attempting to load default board")

            if self.game_service and self.game_instance:
                await self.game_service.select_board("default", game_id=self.game_instance.game_id)
                return "default"
            elif not self.game_instance:
                logger.error("Cannot load default board - game_instance not set on BoardManager")
            else:
                logger.error("Cannot load default board - game service not available")
                return None
                
        except Exception as e:
            logger.error(f"Error loading default board: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None 