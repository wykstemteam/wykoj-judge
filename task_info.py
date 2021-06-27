from dataclasses import dataclass
from typing import List, Optional

from language import Language


@dataclass
class TestCase:
    subtask: int
    test_case: int
    input: str
    output: Optional[str]  # null if have grader


@dataclass
class TaskInfo:
    time_limit: float  # seconds
    memory_limit: int  # megabytes
    grader: bool  # if uses grader
    grader_source_code: Optional[str]
    grader_language: Optional[Language]
    test_cases: List[TestCase]
