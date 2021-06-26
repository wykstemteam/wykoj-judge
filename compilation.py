import shutil
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
    code_path = f'run/code{thread_id}.{submission.language}'
    executable_path = f'run/code{thread_id}.exe'
    metadata_path = f'run/metadata{thread_id}.txt'
    with open(code_path, 'w') as f:
        f.write(submission.code)  # write to run\codeX.xxx

    if submission.language == Languages.cpp:
        compile_proc = subprocess.run(['g++', '-O2', '-o', executable_path, code_path],
                                      text=True,
                                      stderr=subprocess.DEVNULL)
        if compile_proc.returncode != 0:
            return Verdict.CE

        # initialises isolate sandbox
        init_proc = subprocess.run(['isolate', '-b', str(thread_id), '--init'], stdout=subprocess.PIPE)
        if init_proc.returncode != 0:
            return Verdict.IE

        box_path = f'{init_proc.stdout}/box'
        shutil.copy(code_path, box_path)  # copies executable to sandbox

        time_limit = 1.0  # in seconds
        memory_limit = 1024  # in megabytes

        run_proc = subprocess.run(['isolate',
                                   '-M', metadata_path,  # metadata
                                   '-b', str(thread_id),  # sandbox id
                                   '-t', str(time_limit),
                                   '-w', str(time_limit + 1),  # wall time to prevent sleeping programs
                                   '-m', str(memory_limit * 1024),  # in kilobytes
                                   '--stderr-to-stdout',
                                   '--silent',  # tells isolate to be silent
                                   '--run', f'code{thread_id}'],
                                  input='placeholder',
                                  text=True,
                                  stdin=subprocess.PIPE)
        if run_proc.returncode != 0:
            return Verdict.IE
        with open(metadata_path) as f:
            print(f.read())
        return Verdict.AC
