import os
from typing import Iterable
import itertools

import judge.constants as constants

from .models import TaskInfo, TestCase


class TestCaseManager:
    def read_file(path: str) -> str:
        with open(path) as f:
            return f.read()

    @staticmethod
    def iter_test_cases(task_info: TaskInfo) -> Iterable[TestCase]:
        dir_path = os.path.join(constants.TEST_CASES_DIR, task_info.task_id)
        files = os.listdir(dir_path)

        if task_info.grader:
            for i in itertools.count(1):
                for j in itertools.count(1):
                    if f"{i}.{j}.in" in files:
                        case_in = TestCaseManager.read_file(os.path.join(dir_path, f"{i}.{j}.in"))
                        yield TestCase(subtask=i, test_case=j, input=case_in)
                    elif j == 1:
                        return
                    else:
                        break
        else:
            for i in itertools.count(1):
                for j in itertools.count(1):
                    if f"{i}.{j}.in" in files and f"{i}.{j}.out" in files:
                        case_in = TestCaseManager.read_file(os.path.join(dir_path, f"{i}.{j}.in"))
                        case_out = TestCaseManager.read_file(os.path.join(dir_path, f"{i}.{j}.out"))
                        yield TestCase(subtask=i, test_case=j, input=case_in, output=case_out)
                    elif j == 1:
                        return
                    else:
                        break
