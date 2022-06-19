from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel

from .language import Language
from .verdict import Verdict

# FastAPI models


class Submission(BaseModel):
    id: int
    language: Language
    source_code: str


class TaskInfo(BaseModel):
    task_id: str
    time_limit: float  # seconds
    memory_limit: int  # megabytes
    grader: bool  # if uses grader
    grader_source_code: Optional[str] = None
    grader_language: Optional[Language] = None


class JudgeRequest(BaseModel):
    task_info: TaskInfo
    submission: Submission


# Other models


@dataclass
class TestCase:
    subtask: int
    test_case: int
    input: str
    output: Optional[str] = None  # None if have grader


@dataclass
class TestCaseResult:
    subtask: int
    test_case: int
    verdict: Verdict
    score: float
    time_used: float
    memory_used: float

    def to_dict(self):
        return {
            "subtask": self.subtask,
            "test_case": self.test_case,
            "verdict": self.verdict,
            "score": self.score,
            "time_used": self.time_used,
            "memory_used": self.memory_used
        }
