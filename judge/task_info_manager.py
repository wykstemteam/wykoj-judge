import hashlib
import json
import logging
import os
import queue
import secrets
import threading
import time
from collections import defaultdict
from typing import Any, Dict, Iterable, Optional

import ijson
import requests
from cachetools import TTLCache, cached

import judge.constants as constants
from .common import pending_shutdown
from .task_info import TaskInfo, TestCase


class TaskInfoManager:
    path_dict: Dict[str, str] = {}
    lock = threading.RLock()
    get_task_info_queue = queue.Queue()
    waiting_judge_queue: Dict[str, queue.Queue] = defaultdict(queue.Queue)

    @staticmethod
    def init() -> None:
        if not os.path.exists(constants.TASK_INFO_CACHE_DIR):
            os.mkdir(constants.TASK_INFO_CACHE_DIR)
        if os.path.exists('task_info_path.json'):
            with open('task_info_path.json') as f:
                TaskInfoManager.path_dict = json.load(f)

        # Copy keys since cannot delete during iteration
        for key in tuple(TaskInfoManager.path_dict.keys()):
            # Delete keys in path dict whose file do not exist
            if not os.path.exists(TaskInfoManager.path_dict[key]):
                del TaskInfoManager.path_dict[key]

        for filename in os.listdir(constants.TASK_INFO_CACHE_DIR):
            # Delete files not in path dict
            if (
                f'{constants.TASK_INFO_CACHE_DIR}/{filename}'
                not in TaskInfoManager.path_dict.values()
            ):
                os.remove(f'{constants.TASK_INFO_CACHE_DIR}/{filename}')

    @staticmethod
    def shutdown() -> None:
        with TaskInfoManager.lock:
            with open('task_info_path.json', 'w') as f:
                json.dump(TaskInfoManager.path_dict, f)

    @staticmethod
    def get_current_task_info_path(task_id: str) -> str:
        with TaskInfoManager.lock:
            return TaskInfoManager.path_dict[task_id]

    @staticmethod
    def compute_checksum(task_info_path: str) -> str:
        checksum = hashlib.sha384()
        with open(task_info_path, encoding='utf-8') as f:
            while True:
                chunk = f.read(16 * 1024)
                if not chunk:
                    break
                checksum.update(chunk.encode())
        return checksum.hexdigest()

    @staticmethod
    def get_checksum(task_id: str) -> str:
        response = requests.get(
            f'{constants.FRONTEND_URL}/task/{task_id}/info/checksum',
            headers={'X-Auth-Token': constants.CONFIG['secret_key']}
        )
        checksum = response.json()['checksum']
        return checksum

    @staticmethod
    @cached(TTLCache(maxsize=64, ttl=20))
    def _is_up_to_date(task_id: str, task_info_path: str) -> bool:
        # Checksum of task info may be different (incomplete retrieval / modified by frontend)
        return (
            TaskInfoManager.compute_checksum(task_info_path) ==
            TaskInfoManager.get_checksum(task_id)
        )

    @staticmethod
    def is_up_to_date(task_id: str, task_info_path: Optional[str] = None) -> bool:
        if not task_info_path:
            with TaskInfoManager.lock:
                if task_id not in TaskInfoManager.path_dict:
                    return False
                task_info_path = TaskInfoManager.path_dict[task_id]

        return TaskInfoManager._is_up_to_date(task_id, task_info_path)

    @staticmethod
    def update_task_info(task_id: str) -> None:
        if constants.DEBUG:
            return

        task_info_path = f'{constants.TASK_INFO_CACHE_DIR}/{task_id}_{secrets.token_hex(6)}.json'

        # Stream task info to file
        response = requests.get(
            f'{constants.FRONTEND_URL}/task/{task_id}/info',
            headers={'X-Auth-Token': constants.CONFIG['secret_key']},
            stream=True
        )
        with open(task_info_path, 'w') as f:
            for chunk in response.iter_content(chunk_size=16 * 1024, decode_unicode=True):
                f.write(chunk)

        response.raise_for_status()
        if not TaskInfoManager.is_up_to_date(task_id, task_info_path):
            raise RuntimeError('Task info checksum does not match')

        # Update task info path
        with TaskInfoManager.lock:
            TaskInfoManager.path_dict[task_id] = task_info_path

    @staticmethod
    def pre_update_task_info(task_id: str) -> None:
        with TaskInfoManager.lock:
            logging.info(f"Pushing task_id {task_id} to get_task_info_queue")
            TaskInfoManager.get_task_info_queue.put(task_id)
            logging.info(f"Creating queue.Queue() for waiting_judge_queue[{task_id}]")
            TaskInfoManager.waiting_judge_queue[task_id] = queue.Queue()

    @staticmethod
    def post_update_task_info(task_id: str) -> None:
        # Prevent circular imports
        from .judge_manager import JudgeManager

        with TaskInfoManager.lock:
            task_info_path = TaskInfoManager.path_dict[task_id]
            # Release submissions into judge queue
            if task_id not in TaskInfoManager.waiting_judge_queue:
                logging.warning(f"TaskInfoManager.waiting_judge_queue[{task_id!r}] does not exist")
                return
            logging.debug(f"Releasing {task_id} submissions into judge queue")
            while not TaskInfoManager.waiting_judge_queue[task_id].empty():
                args = TaskInfoManager.waiting_judge_queue[task_id].get_nowait()
                JudgeManager.judge_queue.put((*args, task_info_path))
                TaskInfoManager.waiting_judge_queue[task_id].task_done()
            del TaskInfoManager.waiting_judge_queue[task_id]

    @staticmethod
    def update_task_info_worker() -> None:
        while not pending_shutdown.is_set() or not TaskInfoManager.get_task_info_queue.empty():
            try:
                with TaskInfoManager.lock:
                    task_id = TaskInfoManager.get_task_info_queue.get_nowait()
            except queue.Empty:
                time.sleep(1)
                continue
            TaskInfoManager.update_task_info(task_id)
            TaskInfoManager.post_update_task_info(task_id)

    @staticmethod
    def get_task_info(task_info_path: str) -> Dict[str, Any]:
        # Load task info (metadata) from file
        with open(task_info_path, 'rb') as f:
            metadata = {}
            key = None
            for prefix, event, value in ijson.parse(f, use_float=True):
                if not prefix.startswith("metadata"):
                    continue
                if event == "end_map":
                    break
                elif event == "map_key":
                    key = value
                elif event != "start_map":
                    metadata[key] = value

        return TaskInfo(
            float(metadata['time_limit']), int(metadata['memory_limit']), metadata['grader'],
            metadata.get('grader_source_code'), metadata.get('grader_language')
        )

    @staticmethod
    def iter_test_cases(task_info_path: str) -> Iterable[TestCase]:
        with open(task_info_path, 'rb') as f:
            for test_case in ijson.items(f, 'test_cases.item'):
                yield TestCase(**test_case)
