from pydantic import BaseModel
from typing import List
from .question import Question

class Category(BaseModel):
    name: str
    questions: List[Question]
    
    @classmethod
    def create(cls, name: str, questions_data: List[dict]):
        from .question import Question, Clue, Answer
        
        questions = []
        for q in questions_data:
            question = Question(
                clue=Clue(text=q["clue"]),
                answer=Answer(text=q["answer"]),
                value=q["value"],
                double_big_head=q.get("double_big_head", False),
                type=q.get("type", "text")
            )
            questions.append(question)
            
        return cls(name=name, questions=questions) 