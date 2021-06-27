from pydantic import BaseModel


class Submission(BaseModel):
    source_code: str
