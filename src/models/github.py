from pydantic import BaseModel, Field


class PRFile(BaseModel):
    filename: str
    status: str
    additions: int
    deletions: int
    changes: int
    patch: str = ""
    sha: str
    blob_url: str
    raw_url: str
    contents_url: str


class PullRequest(BaseModel):
    model_config = {"populate_by_name": True}
    
    number: int
    title: str
    body: str | None = None
    state: str
    html_url: str
    head_sha: str = Field(alias="head")
    base_sha: str = Field(alias="base")
    user: dict
    created_at: str
    updated_at: str


class Repository(BaseModel):
    id: int
    name: str
    full_name: str
    private: bool
    html_url: str
    description: str | None = None
    owner: dict
