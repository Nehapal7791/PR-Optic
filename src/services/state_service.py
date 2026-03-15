"""
State Service for PR Review Persistence

Manages PR review state across commits using JSON file storage.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from src.models.state import PRReviewState, OpenIssue, utcnow
from src.models.review import ReviewResult, ReviewScore, Severity
from src.utils.logger import get_logger

logger = get_logger(__name__)


class StateService:
    """Service for managing PR review state."""
    
    def __init__(self, state_dir: str = ".pr_review_state"):
        """Initialize state service.
        
        Args:
            state_dir: Directory to store state files
        """
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(exist_ok=True)
        logger.info(f"StateService initialized with state_dir={self.state_dir}")
    
    def _get_state_file(self, pr_id: str) -> Path:
        """Get path to state file for a PR.
        
        Args:
            pr_id: PR identifier (owner/repo/pr_number)
        
        Returns:
            Path to state file
        """
        # Sanitize pr_id for filename
        safe_id = pr_id.replace("/", "_")
        return self.state_dir / f"{safe_id}.json"
    
    def load(self, pr_id: str) -> PRReviewState | None:
        """Load state for a PR.
        
        Args:
            pr_id: PR identifier (owner/repo/pr_number)
        
        Returns:
            PRReviewState if exists, None otherwise
        """
        state_file = self._get_state_file(pr_id)
        
        if not state_file.exists():
            logger.info(f"No state found for PR {pr_id}")
            return None
        
        try:
            with open(state_file, "r") as f:
                data = json.load(f)
            
            # Parse datetime strings
            if "created_at" in data:
                data["created_at"] = datetime.fromisoformat(data["created_at"])
            if "updated_at" in data:
                data["updated_at"] = datetime.fromisoformat(data["updated_at"])
            
            # Parse open issues
            if "open_issues" in data:
                data["open_issues"] = [
                    OpenIssue(**{
                        **issue,
                        "created_at": datetime.fromisoformat(issue["created_at"]) if "created_at" in issue else utcnow()
                    })
                    for issue in data["open_issues"]
                ]
            
            # Parse score enum
            if "last_review_score" in data:
                data["last_review_score"] = ReviewScore(data["last_review_score"])
            
            state = PRReviewState(**data)
            logger.info(f"Loaded state for PR {pr_id}: {len(state.open_issues)} open issues")
            return state
            
        except Exception as e:
            logger.error(f"Failed to load state for PR {pr_id}: {e}", exc_info=True)
            return None
    
    def save(
        self,
        pr_id: str,
        commit_sha: str,
        review_result: ReviewResult
    ) -> PRReviewState:
        """Save review result as PR state.
        
        Args:
            pr_id: PR identifier (owner/repo/pr_number)
            commit_sha: Commit SHA that was reviewed
            review_result: Review result to save
        
        Returns:
            Saved PRReviewState
        """
        # Convert review comments to open issues
        open_issues = []
        for comment in review_result.comments:
            # Only save critical and major issues
            if comment.severity in [Severity.CRITICAL, Severity.MAJOR]:
                issue = OpenIssue(
                    issue_id=f"{comment.filename}:{comment.line}:{comment.category.value}",
                    filename=comment.filename,
                    line=comment.line,
                    category=comment.category.value,
                    severity=comment.severity,
                    body=comment.body,
                    suggested_fix=comment.suggested_fix
                )
                open_issues.append(issue)
        
        # Create or update state
        existing_state = self.load(pr_id)
        
        state = PRReviewState(
            pr_id=pr_id,
            last_reviewed_commit=commit_sha,
            open_issues=open_issues,
            last_review_score=review_result.score,
            last_review_summary=review_result.summary,
            created_at=existing_state.created_at if existing_state else utcnow(),
            updated_at=utcnow()
        )
        
        # Save to file
        state_file = self._get_state_file(pr_id)
        
        try:
            with open(state_file, "w") as f:
                json.dump(state.model_dump(), f, indent=2, default=str)
            
            logger.info(f"Saved state for PR {pr_id}: {len(open_issues)} open issues")
            return state
            
        except Exception as e:
            logger.error(f"Failed to save state for PR {pr_id}: {e}", exc_info=True)
            raise
    
    def clear(self, pr_id: str) -> bool:
        """Clear state for a PR (when all issues resolved).
        
        Args:
            pr_id: PR identifier (owner/repo/pr_number)
        
        Returns:
            True if cleared, False if no state existed
        """
        state_file = self._get_state_file(pr_id)
        
        if state_file.exists():
            state_file.unlink()
            logger.info(f"Cleared state for PR {pr_id}")
            return True
        
        return False
    
    def list_prs_with_open_issues(self) -> list[str]:
        """List all PRs with open issues.
        
        Returns:
            List of PR IDs with open issues
        """
        pr_ids = []
        
        for state_file in self.state_dir.glob("*.json"):
            try:
                with open(state_file, "r") as f:
                    data = json.load(f)
                
                if data.get("open_issues"):
                    pr_ids.append(data["pr_id"])
                    
            except Exception as e:
                logger.warning(f"Failed to read state file {state_file}: {e}")
        
        logger.info(f"Found {len(pr_ids)} PRs with open issues")
        return pr_ids
