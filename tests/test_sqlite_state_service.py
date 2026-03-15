"""Tests for SQLite-based state service."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime
from src.services.sqlite_state_service import SQLiteStateService
from src.models.state import IssueItem, PRReviewState
from src.models.review import ReviewScore


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def state_service(temp_db):
    """Create state service with temporary database."""
    return SQLiteStateService(db_path=temp_db)


@pytest.fixture
def sample_issues():
    """Sample issues for testing."""
    return [
        IssueItem(
            id="file.py:10:security",
            category="security",
            file="file.py",
            line=10,
            body="SQL injection vulnerability",
            suggested_fix="Use parameterized queries",
            resolved=False,
            round_raised=1
        ),
        IssueItem(
            id="file.py:20:maintainability",
            category="maintainability",
            file="file.py",
            line=20,
            body="Complex function needs refactoring",
            resolved=False,
            round_raised=1
        ),
        IssueItem(
            id="app.py:5:hardcoded_values",
            category="hardcoded_values",
            file="app.py",
            line=5,
            body="API key hardcoded",
            suggested_fix="Use environment variable",
            resolved=False,
            round_raised=1
        )
    ]


class TestSaveAndLoad:
    """Test save and load operations."""
    
    def test_save_creates_state(self, state_service, sample_issues):
        """Test saving PR state creates database entry."""
        pr_id = "owner/repo/1"
        commit_sha = "abc123"
        
        state = state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha=commit_sha,
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found 3 issues",
            round_num=1
        )
        
        assert state is not None
        assert state.pr_id == pr_id
        assert state.last_reviewed_commit == commit_sha
        assert state.round == 1
        assert state.last_review_score == ReviewScore.REQUEST_CHANGES
        assert len(state.all_issues) == 3
    
    def test_load_returns_saved_state(self, state_service, sample_issues):
        """Test loading returns previously saved state."""
        pr_id = "owner/repo/1"
        commit_sha = "abc123"
        
        # Save
        saved_state = state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha=commit_sha,
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found 3 issues"
        )
        
        # Load
        loaded_state = state_service.load(pr_id)
        
        assert loaded_state is not None
        assert loaded_state.pr_id == saved_state.pr_id
        assert loaded_state.last_reviewed_commit == saved_state.last_reviewed_commit
        assert len(loaded_state.all_issues) == len(saved_state.all_issues)
    
    def test_load_returns_none_for_unknown_pr(self, state_service):
        """Test load() returns None for unknown pr_id (not an error)."""
        result = state_service.load("unknown/repo/999")
        
        assert result is None
    
    def test_save_updates_existing_state(self, state_service, sample_issues):
        """Test saving again updates existing state."""
        pr_id = "owner/repo/1"
        
        # First save
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="abc123",
            score=ReviewScore.REQUEST_CHANGES,
            summary="First review"
        )
        
        # Second save with different data
        new_issues = sample_issues[:1]  # Only one issue
        state_service.save(
            pr_id=pr_id,
            issues=new_issues,
            commit_sha="def456",
            score=ReviewScore.COMMENT,
            summary="Second review",
            round_num=2
        )
        
        # Load and verify
        loaded = state_service.load(pr_id)
        assert loaded.last_reviewed_commit == "def456"
        assert loaded.round == 2
        assert len(loaded.all_issues) == 1


class TestUpdateIssue:
    """Test update_issue() operation."""
    
    def test_update_issue_marks_resolved(self, state_service, sample_issues):
        """Test update_issue() marks one issue resolved."""
        pr_id = "owner/repo/1"
        
        # Save state
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="abc123",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues"
        )
        
        # Mark one issue as resolved
        issue_id = sample_issues[0].id
        result = state_service.update_issue(pr_id, issue_id, resolved=True)
        
        assert result is True
        
        # Verify
        loaded = state_service.load(pr_id)
        resolved_issue = next(i for i in loaded.all_issues if i.id == issue_id)
        assert resolved_issue.resolved is True
        
        # Other issues should still be unresolved
        other_issues = [i for i in loaded.all_issues if i.id != issue_id]
        assert all(not i.resolved for i in other_issues)
    
    def test_update_issue_returns_false_for_unknown_issue(self, state_service, sample_issues):
        """Test update_issue() returns False for unknown issue_id."""
        pr_id = "owner/repo/1"
        
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="abc123",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues"
        )
        
        result = state_service.update_issue(pr_id, "nonexistent:issue", resolved=True)
        
        assert result is False
    
    def test_update_issue_can_mark_unresolved(self, state_service, sample_issues):
        """Test update_issue() can mark issue as unresolved."""
        pr_id = "owner/repo/1"
        
        # Create issue that's already resolved
        sample_issues[0].resolved = True
        
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="abc123",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues"
        )
        
        # Mark as unresolved
        issue_id = sample_issues[0].id
        state_service.update_issue(pr_id, issue_id, resolved=False)
        
        # Verify
        loaded = state_service.load(pr_id)
        issue = next(i for i in loaded.all_issues if i.id == issue_id)
        assert issue.resolved is False


class TestMarkApproved:
    """Test mark_approved() operation."""
    
    def test_mark_approved_sets_verdict(self, state_service, sample_issues):
        """Test mark_approved() sets final verdict to approved."""
        pr_id = "owner/repo/1"
        
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="abc123",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues"
        )
        
        result = state_service.mark_approved(pr_id)
        
        assert result is True
        
        # Verify
        loaded = state_service.load(pr_id)
        assert loaded.verdict == ReviewScore.APPROVE
    
    def test_mark_approved_returns_false_for_unknown_pr(self, state_service):
        """Test mark_approved() returns False for unknown PR."""
        result = state_service.mark_approved("unknown/repo/999")
        
        assert result is False


class TestDelete:
    """Test delete() operation."""
    
    def test_delete_clears_state(self, state_service, sample_issues):
        """Test delete() clears state when PR is merged/closed."""
        pr_id = "owner/repo/1"
        
        # Save state
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="abc123",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues"
        )
        
        # Verify it exists
        assert state_service.load(pr_id) is not None
        
        # Delete
        result = state_service.delete(pr_id)
        
        assert result is True
        
        # Verify it's gone
        assert state_service.load(pr_id) is None
    
    def test_delete_returns_false_for_unknown_pr(self, state_service):
        """Test delete() returns False for unknown PR."""
        result = state_service.delete("unknown/repo/999")
        
        assert result is False


class TestPersistence:
    """Test state survives server restart (SQLite file persistence)."""
    
    def test_state_survives_service_restart(self, temp_db, sample_issues):
        """Test state persists across service instances."""
        pr_id = "owner/repo/1"
        commit_sha = "abc123"
        
        # Create first service instance and save
        service1 = SQLiteStateService(db_path=temp_db)
        service1.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha=commit_sha,
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues"
        )
        
        # Create new service instance (simulates server restart)
        service2 = SQLiteStateService(db_path=temp_db)
        
        # Load state with new instance
        loaded = service2.load(pr_id)
        
        assert loaded is not None
        assert loaded.pr_id == pr_id
        assert loaded.last_reviewed_commit == commit_sha
        assert len(loaded.all_issues) == 3
    
    def test_database_file_exists(self, temp_db, sample_issues):
        """Test SQLite file is created and persists."""
        service = SQLiteStateService(db_path=temp_db)
        
        # Save some data
        service.save(
            pr_id="owner/repo/1",
            issues=sample_issues,
            commit_sha="abc123",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Test"
        )
        
        # Verify file exists
        db_path = Path(temp_db)
        assert db_path.exists()
        assert db_path.stat().st_size > 0


class TestIssueItemModel:
    """Test IssueItem model structure."""
    
    def test_issue_item_has_required_fields(self):
        """Test IssueItem model has all required fields."""
        issue = IssueItem(
            id="file.py:10:security",
            category="security",
            file="file.py",
            line=10,
            body="Test issue",
            resolved=False,
            round_raised=1
        )
        
        assert issue.id == "file.py:10:security"
        assert issue.category == "security"
        assert issue.file == "file.py"
        assert issue.line == 10
        assert issue.body == "Test issue"
        assert issue.resolved is False
        assert issue.round_raised == 1
        assert isinstance(issue.created_at, datetime)


class TestPRReviewStateModel:
    """Test PRReviewState model structure."""
    
    def test_pr_review_state_has_required_fields(self, state_service, sample_issues):
        """Test PRReviewState model has all required fields."""
        pr_id = "owner/repo/1"
        
        state = state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="abc123",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Test summary",
            round_num=2
        )
        
        assert state.pr_id == pr_id
        assert isinstance(state.open_issues, list)
        assert isinstance(state.resolved_issues, list)
        assert state.round == 2
        assert state.last_reviewed_commit == "abc123"
        assert state.verdict is None  # Not set yet


class TestUtilityMethods:
    """Test utility methods."""
    
    def test_list_all_prs(self, state_service, sample_issues):
        """Test listing all PRs."""
        # Save multiple PRs
        state_service.save("owner/repo/1", sample_issues, "abc123", ReviewScore.COMMENT, "Test 1")
        state_service.save("owner/repo/2", sample_issues[:1], "def456", ReviewScore.APPROVE, "Test 2")
        
        pr_ids = state_service.list_all_prs()
        
        assert len(pr_ids) == 2
        assert "owner/repo/1" in pr_ids
        assert "owner/repo/2" in pr_ids
    
    def test_get_stats(self, state_service, sample_issues):
        """Test getting database statistics."""
        # Save some data
        state_service.save("owner/repo/1", sample_issues, "abc123", ReviewScore.REQUEST_CHANGES, "Test")
        
        # Mark one issue resolved
        state_service.update_issue("owner/repo/1", sample_issues[0].id, resolved=True)
        
        stats = state_service.get_stats()
        
        assert stats["total_prs"] == 1
        assert stats["total_issues"] == 3
        assert stats["resolved_issues"] == 1
        assert stats["open_issues"] == 2
        assert "db_path" in stats
        assert stats["db_size_bytes"] > 0


class TestMultiplePRs:
    """Test handling multiple PRs."""
    
    def test_multiple_prs_independent(self, state_service, sample_issues):
        """Test multiple PRs maintain independent state."""
        pr1 = "owner/repo/1"
        pr2 = "owner/repo/2"
        
        # Save different states for different PRs
        state_service.save(pr1, sample_issues, "abc123", ReviewScore.REQUEST_CHANGES, "PR 1")
        state_service.save(pr2, sample_issues[:1], "def456", ReviewScore.APPROVE, "PR 2")
        
        # Load and verify independence
        state1 = state_service.load(pr1)
        state2 = state_service.load(pr2)
        
        assert len(state1.all_issues) == 3
        assert len(state2.all_issues) == 1
        assert state1.last_reviewed_commit != state2.last_reviewed_commit
    
    def test_deleting_one_pr_doesnt_affect_others(self, state_service, sample_issues):
        """Test deleting one PR doesn't affect others."""
        pr1 = "owner/repo/1"
        pr2 = "owner/repo/2"
        
        state_service.save(pr1, sample_issues, "abc123", ReviewScore.REQUEST_CHANGES, "PR 1")
        state_service.save(pr2, sample_issues, "def456", ReviewScore.REQUEST_CHANGES, "PR 2")
        
        # Delete PR 1
        state_service.delete(pr1)
        
        # PR 1 should be gone
        assert state_service.load(pr1) is None
        
        # PR 2 should still exist
        assert state_service.load(pr2) is not None
