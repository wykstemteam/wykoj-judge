import os
import subprocess

from languages import Languages
from submission import Submission
from threads_manager import threads_manager
from verdict import Verdict


def judge(submission: Submission, thread_id: int) -> Verdict:
    threads_manager.add_thread(thread_id)
    verdict = _judge_impl(submission, thread_id)
    threads_manager.remove_thread(thread_id)
    return verdict


def _judge_impl(submission: Submission, thread_id: int) -> Verdict:
    print(thread_id)
    code_path = os.path.join('run', f'code{thread_id}.{submission.language}')
    executable_path = os.path.join('run', f'code{thread_id}.exe')
    with open(code_path, 'w') as f:
        f.write(submission.code)  # write to run\codeX.xxx
    if submission.language == Languages.cpp:
        proc = subprocess.run(['g++', '-O2', '-o', executable_path, code_path],
                              text=True,
                              stderr=subprocess.DEVNULL)
        if proc.returncode != 0:
            return Verdict.CE

        proc = subprocess.run([executable_path],
                              input='placeholder',
                              text=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL)
        if proc.returncode != 0:
            return Verdict.RE
        return Verdict.AC
