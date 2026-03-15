from pydantic import BaseModel, Field
from enum import Enum


class ConcernCategory(str, Enum):
    """Categories of code review concerns."""
    HARDCODED_VALUES = "hardcoded_values"
    REUSABILITY = "reusability"
    LOGIC_ERRORS = "logic_errors"
    SECURITY = "security"
    MAINTAINABILITY = "maintainability"
    ENV_CONFIG = "env_config"
    MISSING_ABSTRACTIONS = "missing_abstractions"


class ReviewScore(str, Enum):
    """Review decision scores."""
    APPROVE = "approve"
    COMMENT = "comment"
    REQUEST_CHANGES = "request_changes"


class Severity(str, Enum):
    """Comment severity levels."""
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class TriageResult(BaseModel):
    """Result from first pass triage classification."""
    categories: list[ConcernCategory] = Field(default_factory=list)
    reasoning: str = ""


class ReviewComment(BaseModel):
    """Individual review comment."""
    filename: str
    line: int = Field(gt=0, description="Line number must be > 0")
    category: ConcernCategory
    severity: Severity
    body: str = Field(description="Explanation of the issue")
    suggested_fix: str | None = Field(default=None, description="Suggested code fix")


class ReviewResult(BaseModel):
    """Complete review result from second pass."""
    summary: str
    score: ReviewScore
    comments: list[ReviewComment] = Field(default_factory=list, max_length=10)
    categories_reviewed: list[ConcernCategory] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    """Request to review a pull request."""
    owner: str
    repo: str
    pr_number: int
