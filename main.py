import threading

from fastapi import FastAPI

from compilation import judge
from submission import Submission
from threads_manager import threads_manager

app = FastAPI()
MAX_THREAD_NO = 10


@app.post('/')
def judge_solution(submission: Submission):
    thread_id = threads_manager.get_new_thread_id()
    while thread_id > MAX_THREAD_NO:
        thread_id = threads_manager.get_new_thread_id()
    thread = threading.Thread(target=judge, args=[submission, thread_id], daemon=True)
    thread.start()
    return {}


@app.get('/')
def home():
    return 'hi'
