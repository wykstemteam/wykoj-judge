import json
import logging
import multiprocessing
import os
import shutil
import subprocess
import sys
import threading
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header

import judge.constants as constants

from .common import pending_shutdown, session
from .judge_manager import JudgeManager
from .models import JudgeRequest

if len(sys.argv) >= 2:
    constants.DEBUG = True

logging.basicConfig(
    level=logging.DEBUG if constants.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("debug.log")
    ],
    force=True
)
logger = logging.getLogger(__name__)

app = FastAPI()


@app.get('/ping')
def ping():
    return {'success': True}


def update_test_cases():
    proc = subprocess.run(
        ['git', 'submodule', 'foreach', 'git', 'pull', 'origin', 'master'],
        capture_output=True
    )
    logger.info("[GitHub] Updated test cases\n" + proc.stdout.decode() + proc.stderr.decode())


@app.post("/pull_test_cases")
def pull_test_cases(x_auth_token: Optional[str] = Header(None)):
    if x_auth_token != constants.CONFIG['secret_key']:
        return {'success': False}

    thread = threading.Thread(target=update_test_cases)
    thread.start()
    return {'success': True}


@app.post('/judge')
def judge_solution(judge_request: JudgeRequest, x_auth_token: Optional[str] = Header(None)):
    if x_auth_token != constants.CONFIG['secret_key']:
        return {'success': False}

    JudgeManager.judge_queue.put(judge_request)
    return {'success': True}


def main():
    with open('config.json') as f:
        constants.CONFIG = json.load(f)

    session.headers['X-Auth-Token'] = constants.CONFIG['secret_key']

    if not os.path.exists('run'):
        os.mkdir('run')

    thread = threading.Thread(target=update_test_cases)
    thread.start()

    processes = []
    for i in range(constants.MAX_PROCESS_NO):
        process = multiprocessing.Process(target=JudgeManager.judge_worker, args=(i,))
        process.start()
        processes.append(process)

    uvicorn.run(app, port=8000, host='0.0.0.0', log_config='log_conf.yml')

    pending_shutdown.set()
    logger.info('Waiting for all queued submissions to finish judging')
    for process in processes:
        process.join()

    shutil.rmtree("run")


if __name__ == '__main__':
    main()
