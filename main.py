import threading

from fastapi import FastAPI

from compilation import judge
from submission import Submission
from threads import threads

app = FastAPI()
MAX_THREAD_NO = 10


@app.post('/')
async def judge_solution(submission: Submission):
    thread_id = threads.get_new_thread_id()
    while thread_id > MAX_THREAD_NO:
        thread_id = threads.get_new_thread_id()
    thread = threading.Thread(target=judge, args=[submission, thread_id], daemon=True)
    thread.start()
    return {}
