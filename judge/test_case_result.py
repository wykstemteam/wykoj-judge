from dataclasses import dataclass

from .verdict import Verdict


@dataclass
class TestCaseResult:
    subtask: int
    test_case: int
    verdict: Verdict
    score: float
    time_used: float
    memory_used: float
