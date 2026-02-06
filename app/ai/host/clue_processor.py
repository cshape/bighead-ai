"""
Clue processing for player selections
"""

import logging
import re
from typing import Dict, Any, Optional

from ..utils.llm import LLMClient, LLMConfig

logger = logging.getLogger(__name__)

class ClueProcessor:
    """Processes clue selections from players"""

    def __init__(self):
        """Initialize the clue processor"""
        self.llm_client = LLMClient()
        self.llm_config = LLMConfig(
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        self.game_service = None
        self.game_instance = None

    def set_game_service(self, game_service):
        """Set the game service reference"""
        self.game_service = game_service
        logger.info("Game service set for ClueProcessor")

    def set_game_instance(self, game_instance):
        """Set the game instance reference"""
        self.game_instance = game_instance
        logger.info("Game instance set for ClueProcessor")

    async def process_clue_selection(self, username: str, message: str) -> Dict[str, Any]:
        """
        Process a clue selection message from the player with control.

        Args:
            username: The player's username
            message: The chat message potentially containing a clue selection

        Returns:
            Dictionary with results of the processing, including success status
        """
        try:
            # Skip if game instance is not available
            if not self.game_instance:
                logger.error("Cannot process clue selection - no game instance reference")
                return {"success": False, "error": "Game instance not available"}

            # Get available categories and clues from the game instance
            board = self.game_instance.board
            if not board or "categories" not in board:
                logger.warning("No board loaded in game instance")
                return {"success": False, "error": "No board loaded"}

            # Extract available categories
            available_categories = []
            for category in board["categories"]:
                category_name = category["name"]
                
                # Get available values
                available_values = []
                for question in category["questions"]:
                    if not question.get("used", False):
                        available_values.append(question["value"])
                
                if available_values:
                    available_categories.append({
                        "name": category_name,
                        "available_values": available_values
                    })
            
            if not available_categories:
                logger.warning("No available categories found on the board")
                return {"success": False, "error": "No available categories"}
                
            logger.info(f"Available categories for selection:")
            for cat in available_categories:
                logger.info(f"  Category: {cat['name']}, Values: {cat['available_values']}")
            
            # Build context for the LLM template
            user_context = {
                "player_message": message,
                "available_categories": available_categories
            }
            
            # Log full context for debugging
            logger.info(f"Sending clue selection context to LLM")
            
            # Use LLM to evaluate the clue selection
            response_text = await self.llm_client.chat_with_template(
                user_template="clue_selection_prompt.j2",
                user_context=user_context,
                system_template="clue_selection_evaluation.j2",
                config=self.llm_config
            )
            
            try:
                import json
                response = json.loads(response_text)
                logger.info(f"LLM evaluated clue selection: {json.dumps(response, indent=2)}")
                
                if not response.get("valid", False):
                    error_msg = response.get('error', 'Unknown error')
                    logger.info(f"Invalid clue selection: {error_msg}")
                    return {"success": False, "error": error_msg}
                    
                # Get the category and value
                category_name = response.get("category")
                value = response.get("value")
                
                if not category_name or not value:
                    logger.warning("Category or value missing from LLM response")
                    return {"success": False, "error": "Missing category or value"}
                    
                logger.info(f"Valid clue selection: {category_name} for ${value}")

                # Use the game service to display the question
                game_id = self.game_instance.game_id if self.game_instance else None
                await self.game_service.display_question(category_name, value, game_id=game_id)
                return {"success": True, "category": category_name, "value": value}
                
            except json.JSONDecodeError:
                logger.error(f"Failed to parse LLM response as JSON: {response_text}")
                return {"success": False, "error": "Failed to parse LLM response"}
                
        except Exception as e:
            logger.error(f"Error processing clue selection: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)} 