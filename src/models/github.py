from pydantic import BaseModel


class PRFile(BaseModel):
    filename: str
    status: str
    additions: int
    deletions: int
    patch: str | None = None


class PullRequest(BaseModel):
    number: int
    title: str
    body: str | None
    state: str
    html_url: str
