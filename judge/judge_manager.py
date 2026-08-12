import logging
import multiprocessing
import queue
import traceback

from .judge import judge

logger = logging.getLogger(__name__)


class JudgeManager:
    # Created once in __main__.main() and passed explicitly to worker
    # processes. It must NOT be created here as a class attribute:
    # on platforms using the "spawn" start method (default on macOS),
    # each worker process re-imports this module, which would recreate
    # a brand-new, unconnected queue instead of sharing the parent's.
    judge_queue: multiprocessing.JoinableQueue = None

    @staticmethod
    def judge_worker(
        process_id: int,
        judge_queue: multiprocessing.JoinableQueue,
        pending_shutdown: multiprocessing.Event
    ) -> None:
        while not pending_shutdown.is_set() or not judge_queue.empty():
            try:
                judge_request = judge_queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                judge(judge_request, process_id)
            except Exception as e:
                logger.error(
                    f'Error in judging submission:\n' +
                    ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                )
            judge_queue.task_done()
