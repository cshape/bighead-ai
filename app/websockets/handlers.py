"""
Individual WebSocket message handlers.

Each handler receives a typed Pydantic model payload.
Service references are set at startup via ``init_handlers()``.
"""

import os
import subprocess
import logging
from pathlib import Path
from uuid import uuid4
from fastapi import WebSocket

from .message_router import MessageRouter
from ..models.messages import (
    RegisterPlayerMsg,
    SelectBoardMsg,
    QuestionDisplayMsg,
    DailyDoubleMsg,
    BuzzerMsg,
    AnswerMsg,
    DailyDoubleBetMsg,
    SubmitAnswerMsg,
    ChatMessageMsg,
    AudioCompleteMsg,
    StartGameMsg,
    StartAIGameMsg,
    StartAIHostMsg,
    StopAIGameMsg,
    DismissQuestionMsg,
    BoardInitMsg,
)

logger = logging.getLogger(__name__)

# Module-level service references (set at startup from main.py)
game_service = None
game_manager = None
connection_manager = None
chat_manager = None

router = MessageRouter()


def init_handlers(_game_service, _game_manager, _connection_manager, _chat_manager):
    """Wire up service references. Called once at startup."""
    global game_service, game_manager, connection_manager, chat_manager
    game_service = _game_service
    game_manager = _game_manager
    connection_manager = _connection_manager
    chat_manager = _chat_manager


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@router.route("com.sc2ctl.jeopardy.register_player", RegisterPlayerMsg)
async def handle_register_player(ws: WebSocket, client_id: str, payload: RegisterPlayerMsg, game_id: str, game):
    name = payload.name
    preferences = payload.preferences
    logger.info(f"Registering player: {name} with preferences: {preferences}")

    if not game:
        return

    player_id = None
    registration_success = False

    # Check if player already exists in game state (reconnection or HTTP-join case)
    existing_contestant = game.state.get_contestant_by_name(name)
    if existing_contestant:
        logger.info(f"Player '{name}' is reconnecting, updating websocket key to {client_id}")
        game.state.update_contestant_key(name, client_id)
        game.add_client(client_id)

        player_id = existing_contestant.player_id
        registration_success = True

        await connection_manager.send_personal_message(
            ws,
            "com.sc2ctl.jeopardy.register_player_response",
            {"success": True, "name": name, "player_id": player_id,
             "is_host": game.host_player_id == player_id, "reconnected": True}
        )
    else:
        # Completely new player
        player_id = str(uuid4())

        if game.state.register_contestant(client_id, name, player_id=player_id):
            game.add_client(client_id)

            if preferences and hasattr(game.ai_host, 'game_state_manager'):
                game.ai_host.game_state_manager.add_player_preference(name, preferences)

            if game.host_player_id is None:
                game.host_player_id = player_id

            registration_success = True

            await connection_manager.send_personal_message(
                ws,
                "com.sc2ctl.jeopardy.register_player_response",
                {"success": True, "name": name, "player_id": player_id,
                 "is_host": game.host_player_id == player_id}
            )

    if registration_success:
        player_prefs = {}
        if hasattr(game.ai_host, 'game_state_manager'):
            player_prefs = game.ai_host.game_state_manager.player_preferences

        players_with_prefs = {
            c.name: {
                "score": c.score,
                "preferences": player_prefs.get(c.name, "")
            }
            for c in game.state.contestants.values()
        }

        await connection_manager.broadcast_to_room(
            game_id,
            "com.sc2ctl.jeopardy.player_list",
            {"players": players_with_prefs}
        )
        if game.can_start():
            await connection_manager.broadcast_to_room(
                game_id,
                "com.sc2ctl.jeopardy.game_ready",
                {"ready": True}
            )


@router.route("com.sc2ctl.jeopardy.select_board", SelectBoardMsg)
async def handle_select_board(ws: WebSocket, client_id: str, payload: SelectBoardMsg, game_id: str, game):
    board_id = payload.resolved_board_id
    logger.info(f"Selecting board: {board_id}")
    await game_service.select_board(board_id, game_id=game_id)


@router.route("com.sc2ctl.jeopardy.question_display", QuestionDisplayMsg)
async def handle_question_display(ws: WebSocket, client_id: str, payload: QuestionDisplayMsg, game_id: str, game):
    logger.info(f"Displaying question: {payload.category} - ${payload.value}")
    await game_service.display_question(payload.category, payload.value, game_id=game_id)


@router.route("com.sc2ctl.jeopardy.daily_double", DailyDoubleMsg)
async def handle_daily_double(ws: WebSocket, client_id: str, payload: DailyDoubleMsg, game_id: str, game):
    logger.info(f"Daily double selected: {payload.category} - ${payload.value}")
    await game_service.display_question(payload.category, payload.value, game_id=game_id)


@router.route("com.sc2ctl.jeopardy.buzzer", BuzzerMsg)
async def handle_buzzer(ws: WebSocket, client_id: str, payload: BuzzerMsg, game_id: str, game):
    await game_service.handle_buzz(ws, payload.timestamp, game_id=game_id)


@router.route("com.sc2ctl.jeopardy.answer", AnswerMsg)
async def handle_answer(ws: WebSocket, client_id: str, payload: AnswerMsg, game_id: str, game):
    logger.info(f"Answering question: {'correct' if payload.correct else 'incorrect'}")
    await game_service.answer_question(payload.correct, payload.contestant, game_id=game_id)


@router.route("com.sc2ctl.jeopardy.question_dismiss", DismissQuestionMsg)
async def handle_dismiss_question(ws: WebSocket, client_id: str, payload: DismissQuestionMsg, game_id: str, game):
    await game_service.dismiss_question(game_id=game_id)


@router.route("com.sc2ctl.jeopardy.board_init", BoardInitMsg)
async def handle_board_init(ws: WebSocket, client_id: str, payload: BoardInitMsg, game_id: str, game):
    await game_service.send_categories(game_id=game_id)


@router.route("com.sc2ctl.jeopardy.daily_double_bet", DailyDoubleBetMsg)
async def handle_daily_double_bet(ws: WebSocket, client_id: str, payload: DailyDoubleBetMsg, game_id: str, game):
    logger.info(f"Daily double bet from {payload.contestant}: ${payload.bet}")
    await game_service.handle_daily_double_bet(payload.contestant, payload.bet, game_id=game_id)


@router.route("com.sc2ctl.jeopardy.submit_answer", SubmitAnswerMsg)
async def handle_submit_answer(ws: WebSocket, client_id: str, payload: SubmitAnswerMsg, game_id: str, game):
    # Cancel the answer timeout synchronously BEFORE any await
    if game and game.ai_host and hasattr(game.ai_host, 'buzzer_manager'):
        bm = game.ai_host.buzzer_manager
        if bm.last_buzzer and bm.last_buzzer == payload.contestant:
            bm.cancel_answer_timeout()
            logger.info(f"Cancelled answer timeout for {payload.contestant} — answer submitted via modal")

    # Stop the frontend answer timer
    await connection_manager.broadcast_message(
        "com.sc2ctl.jeopardy.answer_timer_stop",
        {},
        game_id=game_id
    )

    # Echo the answer to chat so all players can see it
    await connection_manager.broadcast_message(
        "com.sc2ctl.jeopardy.chat_message",
        {"username": payload.contestant, "message": payload.answer, "timestamp": None},
        game_id=game_id
    )

    # Process the answer directly, bypassing chat classification
    await game_service.handle_player_answer(payload.contestant, payload.answer, game_id=game_id)


@router.route("com.sc2ctl.jeopardy.chat_message", ChatMessageMsg)
async def handle_chat_message(ws: WebSocket, client_id: str, payload: ChatMessageMsg, game_id: str, game):
    # Cancel the answer timeout synchronously BEFORE any await.
    # If the buzzed player sends a chat message, that IS their answer —
    # the timeout must not fire while the AI evaluates it.
    if game and game.ai_host and hasattr(game.ai_host, 'buzzer_manager'):
        bm = game.ai_host.buzzer_manager
        if bm.last_buzzer and bm.last_buzzer == payload.username:
            bm.cancel_answer_timeout()
            logger.info(f"Cancelled answer timeout for {payload.username} — answer received in chat")
            # Stop the frontend answer timer visual
            await connection_manager.broadcast_message(
                "com.sc2ctl.jeopardy.answer_timer_stop",
                {},
                game_id=game_id
            )

    await chat_manager.handle_message(payload.username, payload.message, game_id=game_id)
    await game_service.handle_chat_message(payload.username, payload.message, game_id=game_id)


@router.route("com.sc2ctl.jeopardy.audio_complete", AudioCompleteMsg)
async def handle_audio_complete(ws: WebSocket, client_id: str, payload: AudioCompleteMsg, game_id: str, game):
    if payload.audio_id:
        logger.info(f"Received audio completion via WebSocket: {payload.audio_id}")
        await game_service.handle_audio_completed(payload.audio_id, game_id=game_id)
    else:
        logger.warning("Received audio completion message without audio_id")


@router.route("com.sc2ctl.jeopardy.start_ai_game", StartAIGameMsg)
async def handle_start_ai_game(ws: WebSocket, client_id: str, payload: StartAIGameMsg, game_id: str, game):
    logger.info("Starting AI game...")
    try:
        project_root = Path(__file__).parent.parent.parent
        standalone_script = project_root / "standalone_ai_player.py"
        os.chmod(standalone_script, 0o755)
        headless_arg = "true" if payload.headless else "false"
        cmd = [str(standalone_script), str(payload.num_players), headless_arg]

        logger.info(f"Launching standalone AI player with: {' '.join(cmd)}")
        subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(project_root)
        )

        await connection_manager.send_personal_message(
            ws,
            "com.sc2ctl.jeopardy.ai_game_started",
            {"status": "success"}
        )
        logger.info("AI game started successfully")
    except Exception as e:
        logger.error(f"Failed to start standalone AI player: {e}")
        await connection_manager.send_personal_message(
            ws,
            "com.sc2ctl.jeopardy.ai_game_started",
            {"status": "error", "message": f"Failed to start AI game: {str(e)}"}
        )


@router.route("com.sc2ctl.jeopardy.stop_ai_game", StopAIGameMsg)
async def handle_stop_ai_game(ws: WebSocket, client_id: str, payload: StopAIGameMsg, game_id: str, game):
    logger.info("Stopping AI game...")
    try:
        if os.name == 'posix':
            subprocess.run(["pkill", "-f", "standalone_ai_player.py"], check=False)
        else:
            subprocess.run(["taskkill", "/f", "/im", "python.exe"], check=False)

        await connection_manager.send_personal_message(
            ws,
            "com.sc2ctl.jeopardy.ai_game_stopped",
            {"status": "success"}
        )
        logger.info("AI game stopped successfully")
    except Exception as e:
        logger.error(f"Failed to stop AI game: {e}")
        await connection_manager.send_personal_message(
            ws,
            "com.sc2ctl.jeopardy.ai_game_stopped",
            {"status": "error", "message": f"Failed to stop AI game: {str(e)}"}
        )


@router.route("com.sc2ctl.jeopardy.start_ai_host", StartAIHostMsg)
async def handle_start_ai_host(ws: WebSocket, client_id: str, payload: StartAIHostMsg, game_id: str, game):
    logger.info("Starting AI host...")
    try:
        await connection_manager.send_personal_message(
            ws,
            "com.sc2ctl.jeopardy.ai_host_started",
            {"status": "success"}
        )
        logger.info("AI host started successfully")
    except Exception as e:
        logger.error(f"Failed to start AI host: {e}")
        await connection_manager.send_personal_message(
            ws,
            "com.sc2ctl.jeopardy.ai_host_started",
            {"status": "error", "message": f"Failed to start AI host: {str(e)}"}
        )


@router.route("com.sc2ctl.jeopardy.start_game", StartGameMsg)
async def handle_start_game(ws: WebSocket, client_id: str, payload: StartGameMsg, game_id: str, game):
    if game:
        player_id = payload.player_id
        if game.host_player_id == player_id or game.is_host(player_id):
            success = await game_manager.start_game(game_id, game_service)
            if success:
                await connection_manager.broadcast_to_room(
                    game_id,
                    "com.sc2ctl.jeopardy.game_started",
                    {"status": "started"}
                )
