"""
State Models for PR Review Tracking

Tracks open issues and review state across commits.
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict
from src.models.review import ReviewScore, Severity


def utcnow():
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class OpenIssue(BaseModel):
    """An open issue from a review that needs verification."""
    
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
    
    issue_id: str  # Unique ID for tracking
    filename: str
    line: int
    category: str
    severity: Severity
    body: str
    suggested_fix: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class PRReviewState(BaseModel):
    """State of a PR review across commits."""
    
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
    
    pr_id: str  # Format: "owner/repo/pr_number"
    last_reviewed_commit: str
    open_issues: list[OpenIssue]
    last_review_score: ReviewScore
    last_review_summary: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class IssueVerification(BaseModel):
    """Result of verifying a single issue fix."""
    
    issue_id: str
    is_fixed: bool
    verification_comment: str
    confidence: float  # 0.0 to 1.0
    
    
class VerificationResult(BaseModel):
    """Result of verifying fixes for a PR."""
    
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
    
    pr_id: str
    commit_sha: str
    total_issues: int
    fixed_issues: int
    still_open_issues: int
    verifications: list[IssueVerification]
    summary: str
    all_fixed: bool
    timestamp: datetime = Field(default_factory=utcnow)
