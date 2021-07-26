import json
import os
import subprocess
import sys
import threading
import traceback
from queue import Queue
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header

import constants
from judge import judge
from language import Language
from submission import Submission

app = FastAPI()
judge_queue = Queue()


@app.get('/')
def home():
    with open('herny.txt', encoding='utf-8') as f:
        return f.read()


@app.post('/judge')
def judge_solution(submission: Submission, submission_id: int, task_id: str, language: Language,
                   x_auth_token: Optional[str] = Header(None)):
    if x_auth_token != constants.CONFIG.get('secret_key'):
        return {'success': False}

    judge_queue.put((submission.source_code, submission_id, task_id, language))
    return {'success': True}


def judge_worker(thread_id: int) -> None:
    while True:
        args = judge_queue.get()
        try:
            judge(*args)
        except Exception as e:
            print(
                f"Error in judging submission:\n" +
                "".join(traceback.format_exception(etype=type(e), value=e, tb=e.__traceback__))
            )
        judge_queue.task_done()


if __name__ == '__main__':
    if len(sys.argv) >= 2:
        constants.DEBUG = True

    # cleanup sandbox
    cleanup_proc = subprocess.run(['isolate', '--silent', '--cleanup'])
    assert cleanup_proc.returncode == 0

    if not os.path.exists('config.json'):
        print('Please add a config.json file. Aborting.')
        sys.exit(1)
    with open('config.json') as f:
        constants.CONFIG = json.load(f)

    for i in range(constants.MAX_THREAD_NO):
        threading.Thread(target=judge_worker, args=(i,), daemon=True).start()

    uvicorn.run(app, port=8000, host='0.0.0.0')

    # Wait for all queued submissions to finish judging
    judge_queue.join()
