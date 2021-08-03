import queue
import traceback

from common import pending_shutdown
from judge import judge


class JudgeManager:
    judge_queue = queue.Queue()

    @staticmethod
    def judge_worker(thread_id: int) -> None:
        while not pending_shutdown.is_set() or not JudgeManager.judge_queue.empty():
            try:
                args = JudgeManager.judge_queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                judge(*args, thread_id)
            except Exception as e:
                print(
                    f'Error in judging submission:\n' +
                    ''.join(traceback.format_exception(etype=type(e), value=e, tb=e.__traceback__))
                )
            JudgeManager.judge_queue.task_done()
