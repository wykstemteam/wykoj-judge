from fastapi import FastAPI

from compilation import judge
from submission import Submission

app = FastAPI()


@app.post("/")
async def judge_solution(submission: Submission):
    verdict = await judge(submission)
    return {'verdict': verdict}
