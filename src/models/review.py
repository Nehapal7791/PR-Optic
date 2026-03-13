from pydantic import BaseModel


class ReviewRequest(BaseModel):
    owner: str
    repo: str
    pr_number: int


class ReviewResult(BaseModel):
    status: str
    comments_posted: int


class CommentItem(BaseModel):
    path: str
    line: int
    body: str
