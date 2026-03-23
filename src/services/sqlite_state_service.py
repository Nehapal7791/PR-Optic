"""
SQLite-based State Service for PR Review Persistence

Provides persistent agent memory across server restarts using SQLite.
This is the agent's memory - tracks issues, resolutions, and review rounds.
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional
from src.models.state import PRReviewState, OpenIssue, utcnow
from src.models.review import ReviewScore, Severity
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SQLiteStateService:
    """SQLite-based state service for persistent PR review memory.
    
    This service provides the agent's memory across webhook events and server restarts.
    All state is persisted to a SQLite database file.
    """
    
    def __init__(self, db_path: str = "pr_review_state.db"):
        """Initialize SQLite state service.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_db()
        logger.info(f"SQLiteStateService initialized with db_path={self.db_path}")
    
    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # PR state table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pr_states (
                    pr_id TEXT PRIMARY KEY,
                    last_reviewed_commit TEXT NOT NULL,
                    round INTEGER NOT NULL DEFAULT 1,
                    last_review_score TEXT NOT NULL,
                    last_review_summary TEXT NOT NULL,
                    verdict TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Issues table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS issues (
                    id TEXT NOT NULL,
                    pr_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    file TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    body TEXT NOT NULL,
                    suggested_fix TEXT,
                    resolved BOOLEAN NOT NULL DEFAULT 0,
                    round_raised INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (pr_id, id),
                    FOREIGN KEY (pr_id) REFERENCES pr_states(pr_id) ON DELETE CASCADE
                )
            """)
            
            # Index for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_issues_pr_id 
                ON issues(pr_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_issues_resolved 
                ON issues(pr_id, resolved)
            """)
            
            conn.commit()
            logger.info("Database schema initialized")
    
    def save(
        self,
        pr_id: str,
        issues: list[OpenIssue],
        commit_sha: str,
        score: ReviewScore = ReviewScore.COMMENT,
        summary: str = "",
        round_num: int = 1
    ) -> PRReviewState:
        """Save PR state and issues to database.
        
        Args:
            pr_id: PR identifier (owner/repo/number)
            issues: List of issues to save
            commit_sha: Commit SHA that was reviewed
            score: Review score
            summary: Review summary
            round_num: Review round number
            
        Returns:
            Saved PRReviewState
        """
        now = utcnow().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if PR state exists
            cursor.execute("SELECT created_at FROM pr_states WHERE pr_id = ?", (pr_id,))
            existing = cursor.fetchone()
            created_at = existing[0] if existing else now
            
            # Upsert PR state
            cursor.execute("""
                INSERT OR REPLACE INTO pr_states 
                (pr_id, last_reviewed_commit, round, last_review_score, 
                 last_review_summary, verdict, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pr_id,
                commit_sha,
                round_num,
                score.value,
                summary,
                None,  # verdict is set separately via mark_approved
                created_at,
                now
            ))
            
            # Delete existing issues for this PR (we'll re-insert)
            cursor.execute("DELETE FROM issues WHERE pr_id = ?", (pr_id,))
            
            # Insert issues
            for issue in issues:
                cursor.execute("""
                    INSERT INTO issues 
                    (id, pr_id, category, file, line, body, suggested_fix, 
                     resolved, round_raised, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    issue.issue_id,
                    pr_id,
                    issue.category,
                    issue.filename,
                    issue.line,
                    issue.body,
                    issue.suggested_fix,
                    False,  # New issues are not resolved
                    round_num,
                    issue.created_at.isoformat()
                ))
            
            conn.commit()
            
        logger.info(f"Saved state for PR {pr_id}: {len(issues)} issues, round {round_num}")
        
        # Return the saved state
        return self.load(pr_id)
    
    def load(self, pr_id: str) -> Optional[PRReviewState]:
        """Load PR state from database.
        
        Args:
            pr_id: PR identifier (owner/repo/number)
            
        Returns:
            PRReviewState if exists, None otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Load PR state
            cursor.execute("""
                SELECT * FROM pr_states WHERE pr_id = ?
            """, (pr_id,))
            
            row = cursor.fetchone()
            if not row:
                logger.info(f"No state found for PR {pr_id}")
                return None
            
            # Load issues
            cursor.execute("""
                SELECT * FROM issues WHERE pr_id = ? ORDER BY created_at
            """, (pr_id,))
            
            issue_rows = cursor.fetchall()
            
            # Build list of unresolved issues
            open_issues_new = []
            
            for issue_row in issue_rows:
                issue = OpenIssue(
                    issue_id=issue_row["id"],
                    category=issue_row["category"],
                    filename=issue_row["file"],
                    line=issue_row["line"],
                    body=issue_row["body"],
                    suggested_fix=issue_row["suggested_fix"],
                    severity=Severity.MAJOR,  # Default, actual severity should be stored in DB
                    created_at=datetime.fromisoformat(issue_row["created_at"])
                )
                
                # Check resolved status from DB row, not from OpenIssue (which doesn't have this field)
                if not bool(issue_row["resolved"]):
                    open_issues_new.append(issue)
            
            # Build PRReviewState - only include unresolved issues in open_issues
            state = PRReviewState(
                pr_id=row["pr_id"],
                last_reviewed_commit=row["last_reviewed_commit"],
                open_issues=open_issues_new,
                last_review_score=ReviewScore(row["last_review_score"]),
                last_review_summary=row["last_review_summary"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"])
            )
            
            logger.info(
                f"Loaded state for PR {pr_id}: "
                f"{len(open_issues_new)} open issues"
            )
            
            return state
    
    def update_issue(self, pr_id: str, issue_id: str, resolved: bool = True) -> bool:
        """Mark a single issue as resolved or unresolved.
        
        Args:
            pr_id: PR identifier
            issue_id: Issue identifier
            resolved: Whether issue is resolved
            
        Returns:
            True if updated, False if issue not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE issues 
                SET resolved = ? 
                WHERE pr_id = ? AND id = ?
            """, (resolved, pr_id, issue_id))
            
            updated = cursor.rowcount > 0
            
            if updated:
                # Update pr_states.updated_at
                cursor.execute("""
                    UPDATE pr_states 
                    SET updated_at = ? 
                    WHERE pr_id = ?
                """, (utcnow().isoformat(), pr_id))
                
                conn.commit()
                logger.info(f"Updated issue {issue_id} in PR {pr_id}: resolved={resolved}")
            else:
                logger.warning(f"Issue {issue_id} not found in PR {pr_id}")
            
            return updated
    
    def mark_approved(self, pr_id: str) -> bool:
        """Mark PR as approved (final verdict).
        
        Args:
            pr_id: PR identifier
            
        Returns:
            True if updated, False if PR not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE pr_states 
                SET verdict = ?, updated_at = ? 
                WHERE pr_id = ?
            """, (ReviewScore.APPROVE.value, utcnow().isoformat(), pr_id))
            
            updated = cursor.rowcount > 0
            conn.commit()
            
            if updated:
                logger.info(f"Marked PR {pr_id} as approved")
            else:
                logger.warning(f"PR {pr_id} not found for approval")
            
            return updated
    
    def delete(self, pr_id: str) -> bool:
        """Delete PR state (when PR is merged/closed).
        
        Args:
            pr_id: PR identifier
            
        Returns:
            True if deleted, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Delete PR state (issues will cascade delete)
            cursor.execute("DELETE FROM pr_states WHERE pr_id = ?", (pr_id,))
            
            deleted = cursor.rowcount > 0
            conn.commit()
            
            if deleted:
                logger.info(f"Deleted state for PR {pr_id}")
            else:
                logger.info(f"No state to delete for PR {pr_id}")
            
            return deleted
    
    def list_all_prs(self) -> list[str]:
        """List all PRs with state.
        
        Returns:
            List of PR IDs
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT pr_id FROM pr_states ORDER BY updated_at DESC")
            
            pr_ids = [row[0] for row in cursor.fetchall()]
            
            logger.info(f"Found {len(pr_ids)} PRs with state")
            return pr_ids
    
    def get_stats(self) -> dict:
        """Get database statistics.
        
        Returns:
            Dict with stats
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM pr_states")
            total_prs = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM issues")
            total_issues = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM issues WHERE resolved = 1")
            resolved_issues = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM issues WHERE resolved = 0")
            open_issues = cursor.fetchone()[0]
            
            return {
                "total_prs": total_prs,
                "total_issues": total_issues,
                "resolved_issues": resolved_issues,
                "open_issues": open_issues,
                "db_path": str(self.db_path),
                "db_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0
            }
