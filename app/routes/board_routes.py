from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any
import logging
import asyncio
import requests

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/board",
    tags=["board"],
)

@router.post("/start-generation")
async def start_board_generation(request: Request):
    """Start the board generation process with placeholder categories."""
    
    logger.info("Starting board generation with placeholders via API")
    
    # Access the game service from app state
    game_service = request.app.state.game_service
    
    # Broadcast to all clients to show placeholder board
    await game_service.connection_manager.broadcast_message(
        "com.sc2ctl.jeopardy.start_board_generation",
        {}
    )
    
    # Also mark the game as ready so the board is shown
    await game_service.connection_manager.broadcast_message(
        "com.sc2ctl.jeopardy.game_ready",
        {"ready": True}
    )
    
    return {"status": "success", "message": "Board generation started"}

@router.post("/reveal-category")
async def reveal_category(request: Request, data: Dict[str, Any]):
    """Reveal a generated category on the board."""
    
    index = data.get("index")
    category = data.get("category")
    
    if index is None or category is None:
        raise HTTPException(status_code=400, detail="Index and category are required")
    
    logger.info(f"Revealing category {index} via API")
    
    # Access the game service from app state
    game_service = request.app.state.game_service
    
    # Broadcast to all clients to reveal this category
    await game_service.connection_manager.broadcast_message(
        "com.sc2ctl.jeopardy.reveal_category",
        {
            "index": index,
            "category": category
        }
    )
    
    return {"status": "success", "message": f"Category {index} revealed"}

@router.post("/select-question")
async def select_question(request: Request, data: Dict[str, Any]):
    """
    API endpoint to select a question on the board by coordinates.
    This is used by the AI host to select questions.
    Requires game_id to identify the game.
    """
    category_index = data.get("categoryIndex")
    value_index = data.get("valueIndex")
    game_id = data.get("game_id")

    if category_index is None or value_index is None:
        raise HTTPException(status_code=400, detail="categoryIndex and valueIndex are required")

    if not game_id:
        raise HTTPException(status_code=400, detail="game_id is required")

    # Access services from app state
    game_service = request.app.state.game_service
    game_manager = request.app.state.game_manager

    # Get the game instance
    game = await game_manager.get_game_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    # Check if a board is loaded
    if not game.board or "categories" not in game.board:
        raise HTTPException(status_code=400, detail="No board loaded for this game")

    # Find the category name based on index
    try:
        categories = game.board["categories"]
        if category_index < 0 or category_index >= len(categories):
            raise HTTPException(status_code=400, detail=f"Invalid category index: {category_index}")

        category = categories[category_index]
        category_name = category["name"]

        # Get question value based on index
        questions = category["questions"]
        if value_index < 0 or value_index >= len(questions):
            raise HTTPException(status_code=400, detail=f"Invalid value index: {value_index}")

        value = questions[value_index]["value"]

        logger.info(f"API selecting question: {category_name} for ${value} (index: {category_index}, {value_index})")

        # Display the question
        await game_service.display_question(category_name, value, game_id=game_id)

        return {
            "status": "success",
            "message": f"Selected question: {category_name} - ${value}"
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error selecting question: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to select question: {str(e)}")

async def _register_question_with_backend(self, category_name, value, category_index, value_index):
    # First, try to get the board ID from the page
    try:
        # Extract current board ID from the page if possible
        board_id = self.browser.execute_script("""
            return window.currentBoardId || document.querySelector('[data-board-id]')?.dataset.boardId;
        """)
        
        logger.info(f"Using board ID: {board_id or 'unknown'}")
        
        # PRIMARY METHOD: WebSocket (this is likely what the frontend uses)
        script = f"""
        const sendMessage = (topic, payload) => {{
            if (window.ws && window.ws.readyState === WebSocket.OPEN) {{
                console.log('Sending message via WebSocket:', topic, payload);
                window.ws.send(JSON.stringify({{ topic, payload }}));
                return true;
            }}
            console.error('WebSocket not ready');
            return false;
        }};
        
        // This matches exactly what the frontend would send
        sendMessage('com.sc2ctl.jeopardy.select_question', {{ 
            categoryIndex: {category_index},
            valueIndex: {value_index},
            categoryName: "{category_name}",
            value: {value},
            boardId: "{board_id or ''}"
        }});
        """
        
        self.browser.execute_script(script)
        logger.info(f"Sent WebSocket message to select question")
        
        # Give the backend time to process the selection
        await asyncio.sleep(1.0)  # Longer delay
        
        # BACKUP METHOD: Try API endpoint if available
        endpoint = "http://localhost:8000/api/board/select-question"
        payload = {
            "categoryIndex": category_index,
            "valueIndex": value_index,
            "categoryName": category_name,
            "value": value,
            "boardId": board_id or ""
        }
        
        try:
            response = requests.post(endpoint, json=payload, timeout=3)
            if response.status_code == 200:
                logger.info(f"API registration successful: {response.json()}")
            else:
                logger.warning(f"API registration failed: {response.status_code}")
        except Exception as e:
            logger.warning(f"API registration error: {e}")
        
        return True
    except Exception as e:
        logger.error(f"Error in question registration: {e}")
        return False

@router.post("/audio-complete")
async def audio_complete(request: Request, data: Dict[str, Any]):
    """
    API endpoint to signal that audio playback has completed.
    This is called by the frontend when audio finishes playing.
    Requires game_id to identify which game the audio belongs to.
    """
    audio_id = data.get("audio_id")
    game_id = data.get("game_id")

    if not audio_id:
        logger.warning("Audio completion notification received without audio_id")
        raise HTTPException(status_code=400, detail="audio_id is required")

    if not game_id:
        logger.warning("Audio completion notification received without game_id")
        raise HTTPException(status_code=400, detail="game_id is required")

    logger.info(f"🔊 Audio playback complete notification received: {audio_id} for game {game_id}")

    # Access the game manager from app state
    game_manager = request.app.state.game_manager
    game = await game_manager.get_game_by_id(game_id)

    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    # Store completion status in the game instance
    game.mark_audio_completed(audio_id)

    # Broadcast completion event to all clients in the game
    game_service = request.app.state.game_service
    await game_service.connection_manager.broadcast_message(
        game_service.AUDIO_COMPLETE_TOPIC,
        {"audio_id": audio_id},
        game_id=game_id
    )

    return {"status": "success", "audio_id": audio_id}

@router.get("/audio-status/{game_id}/{audio_id}")
async def get_audio_status(request: Request, game_id: str, audio_id: str):
    """
    API endpoint to check if audio has completed playing.
    This is used by the AI host to poll for completion status.
    """
    # Access the game manager from app state
    game_manager = request.app.state.game_manager
    game = await game_manager.get_game_by_id(game_id)

    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    # Check if this audio ID has been marked as completed
    completed = game.check_audio_completed(audio_id)

    logger.debug(f"Audio status check for {audio_id} in game {game_id}: completed={completed}")

    return {
        "audio_id": audio_id,
        "game_id": game_id,
        "completed": completed
    }

@router.get("/audio-debug/{game_id}")
async def get_audio_debug(request: Request, game_id: str):
    """
    Debug endpoint to list all completed audio IDs for a game.
    """
    # Access the game manager from app state
    game_manager = request.app.state.game_manager
    game = await game_manager.get_game_by_id(game_id)

    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    # Get the list of completed audio IDs
    completed_ids = list(game.completed_audio_ids)
    completed_count = len(completed_ids)

    # Only return the most recent 20 for readability
    recent_ids = completed_ids[-20:] if len(completed_ids) > 20 else completed_ids

    logger.info(f"Audio debug request for game {game_id}: {completed_count} completed IDs")

    return {
        "game_id": game_id,
        "total_completed": completed_count,
        "recent_completed_ids": recent_ids
    }

@router.post("/play-audio")
async def play_audio(request: Request, data: Dict[str, Any]):
    """
    API endpoint to play audio on all clients.
    This is used by the AI host to play speech.
    """
    audio_url = data.get("audio_url")
    wait_for_completion = data.get("wait_for_completion", True)
    audio_id = data.get("audio_id")  # Optional, will be generated if not provided
    
    if not audio_url:
        logger.warning("Audio playback request received without audio_url")
        raise HTTPException(status_code=400, detail="audio_url is required")
    
    logger.info(f"🔊 Playing audio request: {audio_url}, wait_for_completion: {wait_for_completion}, id: {audio_id or 'auto-generate'}")
    
    # Access the game service from app state
    game_service = request.app.state.game_service
    
    # Use the game service to play audio
    audio_id = await game_service.play_audio(audio_url, wait_for_completion, audio_id)
    
    return {
        "status": "success", 
        "message": f"Audio playback started",
        "audio_id": audio_id
    } 