"""
Pydantic models for WebSocket message validation.

Inbound models validate client -> server messages.
Outbound models document server -> client message shapes.
"""

from pydantic import BaseModel
from typing import Optional, Dict, Any


# --- Inbound (client -> server) ---

class RegisterPlayerMsg(BaseModel):
    name: str
    preferences: str = ""


class SelectBoardMsg(BaseModel):
    boardId: Optional[str] = None
    board_id: Optional[str] = None

    @property
    def resolved_board_id(self) -> Optional[str]:
        return self.boardId or self.board_id


class QuestionDisplayMsg(BaseModel):
    category: str
    value: int


class DailyDoubleMsg(BaseModel):
    category: str
    value: int


class BuzzerMsg(BaseModel):
    contestant: Optional[str] = None
    timestamp: Optional[float] = None


class AnswerMsg(BaseModel):
    contestant: Optional[str] = None
    correct: bool
    value: Optional[int] = None
    answer: Optional[str] = None


class DailyDoubleBetMsg(BaseModel):
    contestant: str
    bet: int


class ChatMessageMsg(BaseModel):
    username: str = "Anonymous"
    message: str = ""
    is_admin: bool = False


class AudioCompleteMsg(BaseModel):
    audio_id: Optional[str] = None


class StartGameMsg(BaseModel):
    player_id: Optional[str] = None


class StartAIGameMsg(BaseModel):
    num_players: int = 3
    headless: bool = True


class StartAIHostMsg(BaseModel):
    pass


class StopAIGameMsg(BaseModel):
    pass


class DismissQuestionMsg(BaseModel):
    pass


class BoardInitMsg(BaseModel):
    pass


# --- Outbound (server -> client, for documentation / type-checking) ---

class RegisterPlayerResponse(BaseModel):
    success: bool
    name: Optional[str] = None
    player_id: Optional[str] = None
    is_host: bool = False
    reconnected: bool = False
    error: Optional[str] = None


class PlayerListPayload(BaseModel):
    players: Dict[str, Any]


class GameStatePayload(BaseModel):
    game_id: str
    game_code: str
    status: str
    players: Dict[str, Any]
    board: Optional[Any] = None
    current_question: Optional[Any] = None
    buzzer_active: bool = False
    last_buzzer: Optional[str] = None
    game_ready: bool = False
    is_host: bool = False


class BuzzerStatusPayload(BaseModel):
    active: bool


class ContestantScorePayload(BaseModel):
    scores: Dict[str, int]
