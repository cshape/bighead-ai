from pydantic import BaseModel
from typing import Optional, Literal

class Clue(BaseModel):
    text: str
    
    def __str__(self) -> str:
        return self.text

class Answer(BaseModel):
    text: str
    
    def __str__(self) -> str:
        return self.text

class Question(BaseModel):
    clue: Clue
    answer: Answer
    value: int
    double_big_head: bool = False
    type: Literal["text", "image", "audio", "video"] = "text"
    used: bool = False
    
    def mark_as_used(self):
        self.used = True
    
    def is_double_big_head(self) -> bool:
        return self.double_big_head 