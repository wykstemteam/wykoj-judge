import shutil
import subprocess

from languages import Languages
from submission import Submission
from threads_manager import threads_manager
from verdict import Verdict


def judge(submission: Submission, thread_id: int) -> Verdict:
    threads_manager.add_thread(thread_id)
    verdict = _judge_impl(submission, thread_id)

    # cleanup sandbox
    cleanup_proc = subprocess.run(['isolate', '-b', str(thread_id), '--cleanup'],
                                  text=True,
                                  stdout=subprocess.PIPE)
    if cleanup_proc.returncode != 0:
        return Verdict.IE

    threads_manager.remove_thread(thread_id)
    return verdict


def _judge_impl(submission: Submission, thread_id: int) -> Verdict:
    code_path = f'run/code{thread_id}.{submission.language}'
    executable_path = f'run/code{thread_id}'
    metadata_path = f'run/metadata{thread_id}.txt'
    with open(code_path, 'w') as f:
        f.write(submission.code)  # write to run\codeX.xxx

    if submission.language == Languages.cpp:
        compile_proc = subprocess.run(['g++', '-O1', '-o', executable_path, code_path],
                                      text=True,
                                      stderr=subprocess.PIPE)
        if compile_proc.returncode != 0:
            return Verdict.CE

        # initialises isolate sandbox
        init_proc = subprocess.run(['isolate', '-b', str(thread_id), '--init'],
                                   text=True,
                                   stdout=subprocess.PIPE)
        if init_proc.returncode != 0:
            return Verdict.IE

        box_path = f'{init_proc.stdout.strip()}/box'
        shutil.copy(executable_path, box_path)  # copies executable to sandbox

        time_limit = 1.0  # in seconds
        memory_limit = 256  # in megabytes

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
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  text=True)

        metadata = {}
        with open(metadata_path) as f:
            for line in f.readlines():
                line = line.strip()
                if line:
                    a, b = line.split(':')
                    metadata[a] = b

        if 'status' in metadata:
            status = metadata['status']
            if status == 'RE' or status == 'SG' or status == 'XX':
                return Verdict.RE
            if status == 'TO':
                return Verdict.TLE
            return Verdict.IE

        return Verdict.AC
