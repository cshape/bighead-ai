from .utils.llm import LLMClient, LLMConfig
from .player import AIPlayer
import asyncio
import json
import logging

from ..utils.logging_config import setup_logging
setup_logging()

logger = logging.getLogger(__name__)

async def test_llm():
    """Test basic LLM functionality."""
    logger.info("Testing basic LLM functionality...")
    llm = LLMClient()
    
    try:
        config = LLMConfig(response_format={"type": "json_object"})
        response = await llm.chat_with_prompt(
            "You are in a Jeopardy game. You are contestant <name>. The scores are currently <scores>. In the category of <category>, the current question for <dollar_amount> is: <question_text>. Generate a JSON object with the following fields: answer <bool> and response <string>", 
            "You are a helpful assistant that generates JSON objects.",
            config
        )
        logger.info(f"LLM response: {response}")
    except Exception as e:
        logger.error(f"Error making LLM call: {e}")

async def test_ai_player():
    """Test AI player functionality."""
    logger.info("Testing AI player functionality...")
    
    # Create an AI player with a personality
    ai_player = AIPlayer(name="Watson", personality="knowledgeable and slightly arrogant")
    
    # Test scenario 1: Question displayed
    question_state = {
        "state": "QUESTION_DISPLAYED",
        "category": "Science",
        "question_text": "This force keeps planets in orbit around the Sun.",
        "value": 400
    }
    
    logger.info("Updating AI player with question state...")
    ai_player.update_state(question_state)
    
    logger.info("Getting AI player action for question...")
    question_response = await ai_player.get_action()
    logger.info(f"AI player response to question: {question_response}")
    
    # Test scenario 2: If AI buzzed in, get their answer
    if question_response.get("action") == "buzz":
        answer_state = {
            "state": "AWAITING_ANSWER",
            "category": "Science",
            "question_text": "This force keeps planets in orbit around the Sun.",
            "value": 400
        }
        
        logger.info("AI buzzed in. Updating state to awaiting answer...")
        ai_player.update_state(answer_state)
        
        logger.info("Getting AI player answer...")
        answer_response = await ai_player.get_action()
        logger.info(f"AI player answer: {answer_response}")
    
    # Test scenario 3: Selecting a question
    selection_state = {
        "state": "SELECTING_QUESTION",
        "available_categories": ["Science", "History", "Literature", "Sports"],
        "available_values": [200, 400, 600, 800, 1000],
        "player_score": 600
    }
    
    logger.info("Updating AI player with selection state...")
    ai_player.update_state(selection_state)
    
    logger.info("Getting AI player selection...")
    selection_response = await ai_player.get_action()
    logger.info(f"AI player question selection: {selection_response}")
    
    # Test scenario 4: Making a wager
    wager_state = {
        "state": "MAKING_WAGER",
        "wager_type": "Daily Double",
        "max_wager": 1000,
        "player_score": 600
    }
    
    logger.info("Updating AI player with wager state...")
    ai_player.update_state(wager_state)
    
    logger.info("Getting AI player wager...")
    wager_response = await ai_player.get_action()
    logger.info(f"AI player wager: {wager_response}")

async def main():
    """Main function to run tests."""
    # Test basic LLM functionality
    await test_llm()
    
    # Test AI player functionality
    await test_ai_player()

if __name__ == "__main__":
    asyncio.run(main())
