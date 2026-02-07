from pydantic import BaseModel
from typing import List, Optional, Dict
from .category import Category
from .contestant import Contestant
from .question import Question
from .finalbighead import FinalBigHeadState

class BuzzerStatus(BaseModel):
    active: bool = False

class BuzzerResolution(BaseModel):
    contestant: Optional[str] = None
    time_ms: Optional[int] = None

class BuzzEvent(BaseModel):
    contestant: str
    timestamp: int
    difference: int

class Resolver(BaseModel):
    buzzes: List[BuzzEvent] = []
    
    def add_buzz(self, buzz: BuzzEvent):
        self.buzzes.append(buzz)
    
    def clear(self):
        self.buzzes = []
    
    def get_first_buzz(self) -> Optional[BuzzEvent]:
        if not self.buzzes:
            return None
        return min(self.buzzes, key=lambda x: x.difference)

class Board(BaseModel):
    contestants: List[Contestant]
    categories: List[Category]
    buzzer_status: BuzzerStatus = BuzzerStatus()
    resolver: Resolver = Resolver()
    final_big_head_state: FinalBigHeadState
    
    def get_contestant_by_name(self, name: str) -> Optional[Contestant]:
        for contestant in self.contestants:
            if contestant.name == name:
                return contestant
        return None
    
    def find_question(self, category_name: str, value: int) -> Optional[Question]:
        for category in self.categories:
            if category.name == category_name:
                for question in category.questions:
                    if question.value == value:
                        return question
        return None
    
    def resolve_buzzes(self) -> BuzzerResolution:
        first_buzz = self.resolver.get_first_buzz()
        if first_buzz is None:
            return BuzzerResolution()
        
        resolution = BuzzerResolution(
            contestant=first_buzz.contestant,
            time_ms=first_buzz.difference
        )
        
        self.resolver.clear()
        return resolution 