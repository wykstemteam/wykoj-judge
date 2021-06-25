from pydantic import BaseModel

from languages import Languages


class Submission(BaseModel):
    code: str
    language: Languages
    task_id: int
