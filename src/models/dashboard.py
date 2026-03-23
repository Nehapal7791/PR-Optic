"""Dashboard API models for manual review and status endpoints."""

from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from src.models.review import ReviewScore, Severity


class ReviewRequest(BaseModel):
    """Request model for manual review trigger."""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "owner": "username",
                "repo": "repository",
                "pull_number": 1
            }
        }
    )
    
    owner: str = Field(..., description="Repository owner", min_length=1)
    repo: str = Field(..., description="Repository name", min_length=1)
    pull_number: int = Field(..., description="Pull request number", gt=0)


class IssueStatus(BaseModel):
    """Status of a single issue."""
    
    issue_id: str
    filename: str
    line: int
    category: str
    severity: Severity
    body: str
    suggested_fix: str | None = None
    created_at: datetime
    is_resolved: bool = False


class PRStatus(BaseModel):
    """Status of a PR review with open and resolved issues."""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "pr_id": "owner/repo/1",
                "commit_sha": "abc123def456",
                "round": 1,
                "verdict": "request_changes",
                "summary": "Found 3 critical issues...",
                "open_issues": [
                    {
                        "issue_id": "file.py:10:security",
                        "filename": "file.py",
                        "line": 10,
                        "category": "security",
                        "severity": "critical",
                        "body": "SQL injection vulnerability",
                        "suggested_fix": "Use parameterized queries",
                        "created_at": "2024-03-14T10:00:00Z",
                        "is_resolved": False
                    }
                ],
                "resolved_issues": [],
                "last_updated": "2024-03-14T10:00:00Z"
            }
        }
    )
    
    pr_id: str
    commit_sha: str
    round: int = Field(..., description="Number of review rounds")
    verdict: ReviewScore
    summary: str
    open_issues: list[IssueStatus]
    resolved_issues: list[IssueStatus] = []
    last_updated: datetime


class ReviewResponse(BaseModel):
    """Response model for manual review."""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "pr_id": "owner/repo/1",
                "score": "request_changes",
                "comments": 5,
                "summary": "Review completed with 5 issues found",
                "processing_time": 12.5
            }
        }
    )
    
    status: str
    pr_id: str
    score: ReviewScore
    comments: int
    summary: str
    processing_time: float
