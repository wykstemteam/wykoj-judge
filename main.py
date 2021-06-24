import os
import subprocess
from enum import Enum

from fastapi import FastAPI
from pydantic import BaseModel


class Languages(str, Enum):
    cpp = 'cpp'
    py = 'py'


class Solution(BaseModel):
    source_code: str
    source_code_language: Languages
    time_limit: int  # milliseconds
    memory_limit: int  # megabytes


class Verdict(str, Enum):
    AC = 'ac'
    CE = 'ce'
    WA = 'wa'
    RTE = 'rte'


app = FastAPI()


@app.post("/")
async def judge_solution(solution: Solution):
    code_path = os.path.join('run', f'code.{solution.source_code_language}')
    executable_path = os.path.join('run', f'code.exe')
    with open(code_path, 'w') as f:
        f.write(solution.source_code)  # write to run\code.xxx

    compilation_result = None
    if solution.source_code_language == Languages.cpp:
        compilation_result = subprocess.run(['g++', '-O2', code_path, '-o', executable_path], capture_output=True)
    elif solution.source_code_language == Languages.py:
        pass

    if compilation_result:
        if compilation_result.returncode != 0:
            return {'verdict': Verdict.CE}
        

    return {}
