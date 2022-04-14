import json
import logging
import multiprocessing
import os
import subprocess
import sys
import threading
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("debug.log")
    ]
)

import constants
from common import pending_shutdown
from judge_manager import JudgeManager
from language import Language
from submission import Submission
from task_info_manager import TaskInfoManager

app = FastAPI()


@app.get('/ping')
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
        TaskInfoManager.pre_update_task_info(task_id)
        with TaskInfoManager.lock:
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

    if not os.path.exists('config.json'):
        logging.error('Please add a config.json file. Aborting.')
        sys.exit(1)
    with open('config.json') as f:
        constants.CONFIG = json.load(f)

    if not os.path.exists('run'):
        os.mkdir('run')

    TaskInfoManager.init()

    processes = []
    threads = []

    for i in range(constants.MAX_PROCESS_NO):
        process = multiprocessing.Process(target=JudgeManager.judge_worker, args=(i,))
        process.start()
        processes.append(process)

    # One thread for updating task info
    thread = threading.Thread(target=TaskInfoManager.update_task_info_worker)
    thread.start()
    threads.append(thread)

    uvicorn.run(app, port=8000, host='0.0.0.0')

    # is this necessary 
    pending_shutdown.set()
    logging.info('Waiting for all queued submissions to finish judging')
    for thread in threads:
        thread.join()
    for process in processes:
        process.join()

    TaskInfoManager.shutdown()


if __name__ == '__main__':
    main()
