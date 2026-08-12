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

from .common import session
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
    env = os.environ.copy()
    github_token = constants.CONFIG.get('GITHUB_TOKEN')
    if github_token:
        # Authenticates git's https://github.com/... requests with this
        # token, scoped only to this subprocess call (never written to
        # disk, e.g. no ~/.git-credentials or .git/config change).
        env['GIT_CONFIG_COUNT'] = '1'
        env['GIT_CONFIG_KEY_0'] = f'url.https://{github_token}@github.com/.insteadOf'
        env['GIT_CONFIG_VALUE_0'] = 'https://github.com/'

    proc = subprocess.run(
        ['git', 'submodule', 'foreach', 'git', 'pull', 'origin', 'master'],
        capture_output=True,
        env=env
    )
    output = proc.stdout.decode() + proc.stderr.decode()
    if proc.returncode != 0:
        logger.error(f"[GitHub] Failed to update test cases\n{output}")
    else:
        logger.info(f"[GitHub] Updated test cases\n{output}")


@app.post("/pull_test_cases")
def pull_test_cases(x_auth_token: Optional[str] = Header(None)):
    if x_auth_token != constants.CONFIG['SECRET_KEY']:
        return {'success': False}

    thread = threading.Thread(target=update_test_cases)
    thread.start()
    return {'success': True}


@app.post('/judge')
def judge_solution(judge_request: JudgeRequest, x_auth_token: Optional[str] = Header(None)):
    if x_auth_token != constants.CONFIG['SECRET_KEY']:
        return {'success': False}

    JudgeManager.judge_queue.put(judge_request)
    return {'success': True}


def main():
    with open('config.json') as f:
        constants.CONFIG = json.load(f)

    session.headers['X-Auth-Token'] = constants.CONFIG['SECRET_KEY']

    if not os.path.exists('run'):
        os.mkdir('run')

    thread = threading.Thread(target=update_test_cases)
    thread.start()

    # Created here (not as a JudgeManager class attribute or a module global)
    # and passed explicitly to each worker process so they work with both the
    # "fork" (Linux) and "spawn" (macOS default) start methods. pending_shutdown
    # must additionally be a multiprocessing.Event rather than a threading one:
    # a threading.Event is copied into each child at fork, so setting it below
    # would never be seen by the workers and the join() would hang forever.
    JudgeManager.judge_queue = multiprocessing.JoinableQueue()
    pending_shutdown = multiprocessing.Event()

    processes = []
    for i in range(constants.MAX_PROCESS_NO):
        process = multiprocessing.Process(
            target=JudgeManager.judge_worker,
            args=(i, JudgeManager.judge_queue, pending_shutdown)
        )
        process.start()
        processes.append(process)

    uvicorn.run(app, port=constants.PORT, host='0.0.0.0', log_config='log_conf.yml')

    pending_shutdown.set()
    logger.info('Waiting for all queued submissions to finish judging')
    for process in processes:
        process.join()

    shutil.rmtree("run")


if __name__ == '__main__':
    main()
