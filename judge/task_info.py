from dataclasses import dataclass
from typing import Optional

from .language import Language


@dataclass
class TaskInfo:
    time_limit: float  # seconds
    memory_limit: int  # megabytes
    grader: bool  # if uses grader
    grader_source_code: Optional[str] = None
    grader_language: Optional[Language] = None


@dataclass
class TestCase:
    subtask: int
    test_case: int
    input: str
    output: Optional[str] = None  # None if have grader
