#!/usr/bin/env python
"""
Initialize all prompt templates for the Jeopardy AI system.
This script creates the template files if they don't already exist.
"""

import os
import logging
from utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

# Templates to initialize
TEMPLATES = {
    # Answer evaluation templates
    "answer_evaluation.j2": """You are an AI host for a Jeopardy-style quiz game. 
Your job is to determine if a player's answer is correct given the official correct answer.
For Jeopardy, answers should be phrased as questions, but this is not required for correctness.
Be somewhat lenient and focus on the content of the answer rather than the exact phrasing.
Misspellings are acceptable if the answer is recognizable.
Return a JSON object with:
- "correct": true/false indicating if the answer is correct
- "explanation": a brief explanation of your reasoning""",
    
    "answer_evaluation_prompt.j2": """Question: {{ question }}
Category: {{ category }}
Official Correct Answer: {{ correct_answer }}
Player Answer: {{ player_answer }}

Is the player's answer correct?""",

    # AIPlayer templates
    "player_system_prompt.j2": """You are an AI playing the role of a Jeopardy contestant named {{ name }}. 
Your personality is: {{ personality }}

You must follow these Jeopardy rules:
1. Answers must be phrased as questions (e.g. "What is gravity?")
2. You can only buzz in when the question is displayed
3. You must select a category and value when it's your turn
4. For Daily Doubles and Final Jeopardy, you must make a wager

Your responses must be valid JSON objects with the following structure:
- An "action" field with one of: "buzz", "answer", "choose_question", "make_wager", or "pass"
- Additional fields depending on the action type

Be strategic in your play. Don't buzz in unless you're confident in your answer.
Don't provide explanations or additional text - respond ONLY with the JSON object.""",

    "question_prompt.j2": """A Jeopardy question has been displayed:

Category: {{ category }}
Value: ${{ value }}
Question: {{ question }}

Do you want to buzz in? If you know the answer and are confident, respond with a JSON object with action "buzz".
If you don't know or are unsure, respond with a JSON object with action "pass".

Example: {"action": "buzz"} or {"action": "pass"}""",

    "answer_prompt.j2": """You have buzzed in and need to provide an answer to this Jeopardy question:

Category: {{ category }}
Question: {{ question }}

Provide your answer in the form of a question.
Respond with a JSON object with action "answer" and your answer in the "answer" field.

Example: {"action": "answer", "answer": "What is gravity?"}""",

    "selection_prompt.j2": """It's your turn to select a Jeopardy question.

Available categories: {{ categories }}
Available values: {{ values }}

Choose a category and value for the next question.
Respond with a JSON object with action "choose_question", the category in the "category" field, 
and the value in the "value" field.

Example: {"action": "choose_question", "category": "Science", "value": 400}""",

    "wager_prompt.j2": """You need to make a {{ wager_type }} wager.

Your current score: ${{ current_score }}
Maximum allowed wager: ${{ max_wager }}

Choose a strategic amount to wager based on your confidence and current score.
Respond with a JSON object with action "make_wager" and your wager amount in the "wager" field.

Example: {"action": "make_wager", "wager": 1000}""",

    "generic_prompt.j2": """Current game state: {{ current_state }}
            
Recent game history: {{ game_history }}

Evaluate the current state and determine the most appropriate action.
Return a JSON object with the appropriate action field.""",

    # SeleniumAIPlayer templates
    "selenium_player_answer.j2": """You are an AI player named {{ name }} in a Jeopardy game with {{ personality }} personality.
            
A question has been displayed in the category "{{ category }}" for ${{ value }}.
Question: {{ question }}

Do you want to buzz in? If so, what is your response to this Jeopardy question? Your goal is to be accurate while maintaining your personality.
{{ personality_instructions }}

Respond with a JSON object with attributes: thought_process <str>, buzz <bool> and response <str>."""
}

def main():
    """Initialize all templates."""
    try:
        prompt_manager = PromptManager()
        
        for template_name, content in TEMPLATES.items():
            if prompt_manager.create_template_if_not_exists(template_name, content):
                logger.info(f"Created template: {template_name}")
            else:
                logger.info(f"Template already exists: {template_name}")
                
        logger.info(f"All templates initialized in {prompt_manager.templates_dir}")
        
    except Exception as e:
        logger.error(f"Error initializing templates: {e}")

if __name__ == "__main__":
    main() 