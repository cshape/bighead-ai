from pydantic import BaseModel
from typing import List, Dict, Optional

class FinalBigHeadClue(BaseModel):
    category: str
    clue: str
    answer: str

class FinalBigHeadQuestionResponse(BaseModel):
    contestant: str
    bet: int
    answer: str

class FinalBigHeadState(BaseModel):
    clue: FinalBigHeadClue
    contestants: List[str]
    bets: Dict[str, int] = {}
    answers: Dict[str, str] = {}

    def set_bet(self, contestant: str, bet: int):
        self.bets[contestant] = bet

    def set_answer(self, contestant: str, answer: str):
        self.answers[contestant] = answer

    def has_bet(self, contestant: str) -> bool:
        return contestant in self.bets

    def has_answer(self, contestant: str) -> bool:
        return contestant in self.answers

    def has_all_bets(self) -> bool:
        return all(contestant in self.bets for contestant in self.contestants)

    def has_all_answers(self) -> bool:
        return all(contestant in self.answers for contestant in self.contestants)

    def get_missing_bets(self) -> List[str]:
        return [c for c in self.contestants if c not in self.bets]

    def get_missing_answers(self) -> List[str]:
        return [c for c in self.contestants if c not in self.answers]

    def get_response(self, contestant: str) -> Optional[FinalBigHeadQuestionResponse]:
        if not self.has_answer(contestant):
            return None

        return FinalBigHeadQuestionResponse(
            contestant=contestant,
            bet=self.bets.get(contestant, 0),
            answer=self.answers.get(contestant, "")
        )
