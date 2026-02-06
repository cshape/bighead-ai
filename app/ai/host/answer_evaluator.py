"""
Answer evaluation for Jeopardy questions
"""

import logging
import os
import re
from typing import Dict, Any, Optional

from ..utils.llm import LLMClient, LLMConfig

logger = logging.getLogger(__name__)

class AnswerEvaluator:
    """Evaluates player answers for correctness using LLM"""
    
    def __init__(self):
        """Initialize the answer evaluator"""
        self.llm_client = LLMClient()
        self.llm_config = LLMConfig(
            temperature=0.3,
            response_format={"type": "json_object"}
        )
    
    async def evaluate_answer(self, expected_answer: str, player_answer: str,
                            include_explanation: bool = False) -> Dict[str, Any]:
        """
        Use LLM to evaluate if the player's answer is correct.

        Args:
            expected_answer: The correct answer from the board
            player_answer: The player's submitted answer
            include_explanation: Whether to include explanation in response

        Returns:
            Dictionary with evaluation results: {'is_correct': bool, 'explanation': str}
        """
        logger.info(f"Evaluating answer: '{player_answer}' against correct answer: '{expected_answer}'")

        # TEST_MODE: simple string matching instead of LLM
        if os.environ.get("TEST_MODE"):
            # Strip HTML tags from expected answer
            clean_expected = re.sub(r'<[^>]+>', '', expected_answer).strip().lower()
            # Strip "what is", "who is" etc. prefixes from player answer
            clean_player = re.sub(r'^(what|who|where|when)\s+(is|are|was|were)\s+', '', player_answer.strip().lower())
            clean_player = clean_player.strip('? ')
            is_correct = clean_player in clean_expected or clean_expected in clean_player
            logger.info(f"TEST_MODE: '{clean_player}' vs '{clean_expected}' = {is_correct}")
            return {"is_correct": is_correct, "explanation": "Test mode"}
        
        try:
            # Use template-based approach for the prompt
            user_context = {
                "correct_answer": expected_answer,
                "player_answer": player_answer
            }
            
            response_text = await self.llm_client.chat_with_template(
                user_template="answer_evaluation_prompt.j2",
                user_context=user_context,
                system_template="answer_evaluation.j2",
                config=self.llm_config
            )
            
            try:
                import json
                response = json.loads(response_text)
                is_correct = response.get("correct", False)
                explanation = response.get("explanation", "No explanation provided") if include_explanation else ""
                
                logger.info(f"LLM evaluation: correct={is_correct}, reason: {explanation}")
                return {"is_correct": is_correct, "explanation": explanation}
            except json.JSONDecodeError:
                logger.error(f"Failed to parse LLM response as JSON: {response_text}")
                return {"is_correct": False, "explanation": "Error evaluating answer."}
                
        except Exception as e:
            logger.error(f"Error evaluating answer: {e}")
            return {"is_correct": False, "explanation": "Error evaluating answer."}
    
    async def verbalize_answer_result(self, player_name: str, is_correct: bool) -> str:
        """
        Generate a message about whether the answer was correct or not.
        
        Args:
            player_name: The name of the player who answered
            is_correct: Whether the answer was correct
            
        Returns:
            A verbalization of the answer result
        """
        import random
        
        if is_correct:
            responses = [
                f"That's correct, {player_name}! You have control of the board.",
                f"Yes, {player_name}, that's right! You now have control of the board.",
                f"Correct, {player_name}! You have control of the board!",
                f"Well done, {player_name}! The board is yours."
            ]
        else:
            responses = [
                f"I'm sorry, {player_name}, that's incorrect.",
                f"No, {player_name}, that's not right.",
                f"That's incorrect, {player_name}.",
                f"Sorry, {player_name}, that's not the answer we're looking for."
            ]
        
        response = random.choice(responses)
        logger.info(f"Verbalized answer result: {response}")
        return response 