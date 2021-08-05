import json
import os
import subprocess
import sys
import threading
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header

import constants
from common import pending_shutdown
from judge_manager import JudgeManager
from language import Language
from submission import Submission
from task_info_manager import TaskInfoManager

app = FastAPI()


@app.get('/judge')
def ping():
    return {'success': True}


@app.post('/judge')
def judge_solution(submission: Submission, submission_id: int, task_id: str, language: Language,
                   x_auth_token: Optional[str] = Header(None)):
    if x_auth_token != constants.CONFIG['secret_key']:
        return {'success': False}

    with TaskInfoManager.lock:
        if task_id in TaskInfoManager.waiting_judge_queue:
            # Task info is being updated
            TaskInfoManager.waiting_judge_queue[task_id].put(
                (submission.source_code, submission_id, language)
            )
            return {'success': True}

    if not TaskInfoManager.is_up_to_date(task_id):
        # Task info needs to be updated
        with TaskInfoManager.lock:
            TaskInfoManager.pre_update_task_info(task_id)
            TaskInfoManager.waiting_judge_queue[task_id].put(
                (submission.source_code, submission_id, language)
            )
        return {'success': True}

    task_info_path = TaskInfoManager.get_current_task_info_path(task_id)
    JudgeManager.judge_queue.put((submission.source_code, submission_id, language, task_info_path))
    return {'success': True}


def main():
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

    TaskInfoManager.init()

    threads = []

    for i in range(constants.MAX_THREAD_NO):
        thread = threading.Thread(target=JudgeManager.judge_worker, args=(i,))
        thread.start()
        threads.append(thread)

    # One thread for updating task info
    thread = threading.Thread(target=TaskInfoManager.update_task_info_worker)
    thread.start()
    threads.append(thread)

    uvicorn.run(app, port=8000, host='0.0.0.0')

    pending_shutdown.set()
    print('Waiting for all queued submissions to finish judging')
    for thread in threads:
        thread.join()

    TaskInfoManager.shutdown()


if __name__ == '__main__':
    main()
