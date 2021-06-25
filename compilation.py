import os
import asyncio

from languages import Languages
from submission import Submission
from verdict import Verdict


async def judge(submission: Submission) -> Verdict:
    code_path = os.path.join('run', f'code.{submission.language}')
    executable_path = os.path.join('run', f'code.exe')
    with open(code_path, 'w') as f:
        f.write(submission.code)  # write to run\code.xxx
    if submission.language == Languages.cpp:
        proc = await asyncio.create_subprocess_shell(
            f'g++ -O2 -o {executable_path} {code_path}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return Verdict.CE

        proc = await asyncio.create_subprocess_shell(
            f'{code_path}',
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate(
            input='placeholder'.encode('utf-8'),
        )
        if proc.returncode != 0:
            return Verdict.RE
        return Verdict.AC
