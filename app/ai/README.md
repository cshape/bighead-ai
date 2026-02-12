# AI Players for Big Head Game

This module implements AI players that can participate in Big Head games alongside human players.

## Overview

AI players use Large Language Models (LLMs) to make decisions in the game based on the current game state. They can:
- Buzz in when they know the answer
- Provide answers to questions
- Choose categories and questions when it's their turn
- Make wagers for Double Big Heads and Final Big Head

## Game State Machine

The AI players operate based on a state machine representing the game flow:

| State                | Description                                       |
|----------------------|---------------------------------------------------|
| `QUESTION_DISPLAYED` | A question is displayed and buzzer is open        |
| `PLAYER_BUZZED_IN`   | A player (AI or human) has buzzed in              |
| `AWAITING_ANSWER`    | An AI player needs to provide an answer           |
| `SELECTING_QUESTION` | An AI player is selecting the next question       |
| `MAKING_WAGER`       | An AI player needs to make a wager                |
| `GAME_OVER`          | The game has concluded                            |

## AI Player Implementation

The `AIPlayer` class:
- Maintains a reference to the current game state
- Receives updates when game state changes
- Uses the LLM to decide when to take actions
- Returns standardized JSON responses for different game actions

## LLM Integration

The AI players use our LLM client to generate responses in the format:

```json
{
  "action": "<action_type>",
  "answer": "<answer_text>",  // Optional, included when action is "answer"
  "category": "<category>",   // Optional, included when action is "choose_question"
  "value": 400,               // Optional, included when action is "choose_question"
  "wager": 1000               // Optional, included when action is "make_wager"
}
```

Valid actions include:
- `buzz`: The AI wants to buzz in
- `answer`: The AI is providing an answer
- `choose_question`: The AI is selecting the next question
- `make_wager`: The AI is making a wager
- `pass`: The AI chooses not to take action

## Example Usage

```python
# Initialize an AI player
ai_player = AIPlayer(name="AI Watson", personality="confident and knowledgeable")

# Update game state
state = {
    "state": "QUESTION_DISPLAYED",
    "category": "Science",
    "question_text": "This force keeps planets in orbit around the Sun.",
    "value": 400
}
ai_player.update_state(state)

# Get AI response
response = await ai_player.get_action()
# Example response: {"action": "buzz"}

# If AI buzzed in, get their answer
if response["action"] == "buzz":
    state["state"] = "AWAITING_ANSWER"
    ai_player.update_state(state)
    answer_response = await ai_player.get_action()
    # Example: {"action": "answer", "answer": "What is gravity?"}
```

## Implementation Details

1. The AI players use a system prompt that includes:
   - Rules of Big Head
   - Personality traits specific to the AI player
   - Instructions to format responses as JSON

2. For each action, the LLM is provided with:
   - Current game state
   - Game history (previous questions, answers, scores)
   - Instructions specific to the current state 