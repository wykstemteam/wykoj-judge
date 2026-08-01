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
        """
        Send an iterable of subtask numbers (ints) after receiving a
        TestCase to mark those subtasks as skipped: their remaining
        test cases will be yielded without reading input/output files
        from disk. Send None (or nothing) to read normally.
        """
        dir_path = os.path.join(constants.TEST_CASES_DIR, task_info.task_id)
        files = os.listdir(dir_path)
        skipped_subtasks = set()

        if task_info.grader:
            for i in itertools.count(1):
                for j in itertools.count(1):
                    if f"{i}.{j}.in" in files:
                        if i in skipped_subtasks:
                            test_case = TestCase(subtask=i, test_case=j, input='', skip=True)
                        else:
                            case_in = TestCaseManager.read_file(os.path.join(dir_path, f"{i}.{j}.in"))
                            test_case = TestCase(subtask=i, test_case=j, input=case_in)
                        newly_skipped = yield test_case
                        if newly_skipped:
                            skipped_subtasks.update(newly_skipped)
                    elif j == 1:
                        return
                    else:
                        break
        else:
            for i in itertools.count(1):
                for j in itertools.count(1):
                    if f"{i}.{j}.in" in files and f"{i}.{j}.out" in files:
                        if i in skipped_subtasks:
                            test_case = TestCase(subtask=i, test_case=j, input='', skip=True)
                        else:
                            case_in = TestCaseManager.read_file(os.path.join(dir_path, f"{i}.{j}.in"))
                            case_out = TestCaseManager.read_file(os.path.join(dir_path, f"{i}.{j}.out"))
                            test_case = TestCase(subtask=i, test_case=j, input=case_in, output=case_out)
                        newly_skipped = yield test_case
                        if newly_skipped:
                            skipped_subtasks.update(newly_skipped)
                    elif j == 1:
                        return
                    else:
                        break
