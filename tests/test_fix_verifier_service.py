"""Tests for fix verifier service - the re-review loop brain."""

import pytest
from unittest.mock import AsyncMock, MagicMock
import tempfile
from pathlib import Path
from src.services.fix_verifier_service import FixVerifierService
from src.services.sqlite_state_service import SQLiteStateService
from src.services.github_service import GitHubService
from src.services.providers.claude_provider import ClaudeProvider
from src.models.state import OpenIssue, VerificationResult
from src.models.review import ReviewScore


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    yield db_path
    
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def state_service(temp_db):
    """Create state service with temporary database."""
    return SQLiteStateService(db_path=temp_db)


@pytest.fixture
def mock_github_service():
    """Create mock GitHub service."""
    service = MagicMock(spec=GitHubService)
    service.get_commit_diff = AsyncMock()
    service.post_review = AsyncMock()
    return service


@pytest.fixture
def mock_claude_provider():
    """Create mock Claude provider."""
    provider = MagicMock(spec=ClaudeProvider)
    provider.generate = AsyncMock()
    return provider


@pytest.fixture
def verifier_service(state_service, mock_github_service, mock_claude_provider):
    """Create fix verifier service with mocked dependencies."""
    return FixVerifierService(
        state_service=state_service,
        github_service=mock_github_service,
        claude_provider=mock_claude_provider
    )


@pytest.fixture
def sample_issues():
    """Sample issues for testing."""
    from src.models.review import Severity
    return [
        OpenIssue(
            issue_id="app.py:10:security",
            category="security",
            filename="app.py",
            line=10,
            severity=Severity.CRITICAL,
            body="Security issue"
        ),
        OpenIssue(
            issue_id="app.py:20:maintainability",
            category="maintainability",
            filename="app.py",
            line=20,
            severity=Severity.MAJOR,
            body="Maintainability issue"
        ),
        OpenIssue(
            issue_id="config.py:5:hardcoded_values",
            category="hardcoded_values",
            filename="config.py",
            line=5,
            severity=Severity.MAJOR,
            body="Hardcoded value"
        )
    ]


class TestVerifyFixesBasic:
    """Test basic verify_fixes functionality."""
    
    @pytest.mark.asyncio
    async def test_no_previous_state_returns_empty_result(
        self,
        verifier_service
    ):
        """Test verify_fixes returns empty result when no previous state exists."""
        result = await verifier_service.verify_fixes(
            owner="test",
            repo="repo",
            pull_number=1,
            new_commit_sha="abc123"
        )
        
        assert result.total_issues == 0
        assert result.fixed_issues == 0
        assert result.still_open_issues == 0
        assert "No previous review found" in result.summary
        assert result.all_fixed is False
    
    @pytest.mark.asyncio
    async def test_already_verified_commit_skips_verification(
        self,
        verifier_service,
        state_service,
        sample_issues
    ):
        """Test that already-verified commit SHA is skipped."""
        pr_id = "test/repo/1"
        commit_sha = "abc123"
        
        # Save state with this commit
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha=commit_sha,
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues"
        )
        
        # Try to verify same commit again
        result = await verifier_service.verify_fixes(
            owner="test",
            repo="repo",
            pull_number=1,
            new_commit_sha=commit_sha
        )
        
        assert "Already verified" in result.summary
        assert result.total_issues == 3
    
    @pytest.mark.asyncio
    async def test_no_open_issues_returns_all_fixed(
        self,
        verifier_service,
        state_service,
        sample_issues
    ):
        """Test that when all issues are resolved, returns all_fixed=True."""
        pr_id = "test/repo/1"
        
        # Mark all issues as resolved
        for issue in sample_issues:
            issue.resolved = True
        
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="old_commit",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues"
        )
        
        result = await verifier_service.verify_fixes(
            owner="test",
            repo="repo",
            pull_number=1,
            new_commit_sha="new_commit"
        )
        
        assert result.all_fixed is True
        assert result.still_open_issues == 0
        assert "All issues already resolved" in result.summary


class TestVerifyFixesWithMocks:
    """Test verify_fixes with mocked Claude and GitHub responses."""
    
    @pytest.mark.asyncio
    async def test_all_issues_fixed_posts_approve(
        self,
        verifier_service,
        state_service,
        mock_github_service,
        mock_claude_provider,
        sample_issues
    ):
        """Test that when all issues are fixed, APPROVE review is posted."""
        pr_id = "test/repo/1"
        
        # Save state with open issues
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="old_commit",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found 3 issues"
        )
        
        # Mock GitHub diff
        mock_github_service.get_commit_diff.return_value = "diff --git a/app.py..."
        
        # Mock Claude response - different response per category
        # Categories: hardcoded_values, maintainability, security (alphabetical order)
        mock_claude_provider.generate.side_effect = [
            # hardcoded_values category
            """{"verifications": [{"issue_id": "config.py:5:hardcoded_values", "is_fixed": true, "comment": "API key moved to environment variable", "confidence": 0.98}]}""",
            # maintainability category
            """{"verifications": [{"issue_id": "app.py:20:maintainability", "is_fixed": true, "comment": "Function refactored into smaller methods", "confidence": 0.90}]}""",
            # security category
            """{"verifications": [{"issue_id": "app.py:10:security", "is_fixed": true, "comment": "SQL injection fixed with parameterized queries", "confidence": 0.95}]}"""
        ]
        
        # Verify fixes
        result = await verifier_service.verify_fixes(
            owner="test",
            repo="repo",
            pull_number=1,
            new_commit_sha="new_commit"
        )
        
        # Assertions
        assert result.total_issues == 3
        assert result.fixed_issues == 3
        assert result.still_open_issues == 0
        assert result.all_fixed is True
        assert "Excellent work" in result.summary
        
        # Verify GitHub review was posted with APPROVE
        mock_github_service.post_review.assert_called_once()
        call_args = mock_github_service.post_review.call_args
        assert call_args.kwargs["event"] == "APPROVE"
        assert "Re-Review Results" in call_args.kwargs["body"]
    
    @pytest.mark.asyncio
    async def test_some_issues_fixed_posts_request_changes(
        self,
        verifier_service,
        state_service,
        mock_github_service,
        mock_claude_provider,
        sample_issues
    ):
        """Test that when some issues remain, REQUEST_CHANGES review is posted."""
        pr_id = "test/repo/1"
        
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="old_commit",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found 3 issues"
        )
        
        mock_github_service.get_commit_diff.return_value = "diff --git a/app.py..."
        
        # Mock Claude response - only 2 out of 3 fixed
        mock_claude_provider.generate.side_effect = [
            # hardcoded_values - fixed
            """{"verifications": [{"issue_id": "config.py:5:hardcoded_values", "is_fixed": true, "comment": "API key moved to env var", "confidence": 0.98}]}""",
            # maintainability - NOT fixed
            """{"verifications": [{"issue_id": "app.py:20:maintainability", "is_fixed": false, "comment": "Function still too complex", "confidence": 0.85}]}""",
            # security - fixed
            """{"verifications": [{"issue_id": "app.py:10:security", "is_fixed": true, "comment": "SQL injection fixed", "confidence": 0.95}]}"""
        ]
        
        result = await verifier_service.verify_fixes(
            owner="test",
            repo="repo",
            pull_number=1,
            new_commit_sha="new_commit"
        )
        
        assert result.total_issues == 3
        assert result.fixed_issues == 2
        assert result.still_open_issues == 1
        assert result.all_fixed is False
        assert "Good progress" in result.summary
        
        # Verify REQUEST_CHANGES was posted
        call_args = mock_github_service.post_review.call_args
        assert call_args.kwargs["event"] == "REQUEST_CHANGES"
    
    @pytest.mark.asyncio
    async def test_no_issues_fixed_posts_request_changes(
        self,
        verifier_service,
        state_service,
        mock_github_service,
        mock_claude_provider,
        sample_issues
    ):
        """Test that when no issues are fixed, REQUEST_CHANGES is posted."""
        pr_id = "test/repo/1"
        
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="old_commit",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found 3 issues"
        )
        
        mock_github_service.get_commit_diff.return_value = "diff --git a/app.py..."
        
        # Mock Claude response - nothing fixed
        mock_claude_provider.generate.side_effect = [
            # hardcoded_values - NOT fixed
            """{"verifications": [{"issue_id": "config.py:5:hardcoded_values", "is_fixed": false, "comment": "API key still hardcoded", "confidence": 0.95}]}""",
            # maintainability - NOT fixed
            """{"verifications": [{"issue_id": "app.py:20:maintainability", "is_fixed": false, "comment": "Function not refactored", "confidence": 0.85}]}""",
            # security - NOT fixed
            """{"verifications": [{"issue_id": "app.py:10:security", "is_fixed": false, "comment": "SQL injection still present", "confidence": 0.90}]}"""
        ]
        
        result = await verifier_service.verify_fixes(
            owner="test",
            repo="repo",
            pull_number=1,
            new_commit_sha="new_commit"
        )
        
        assert result.fixed_issues == 0
        assert result.still_open_issues == 3
        assert "not been addressed" in result.summary


class TestGroupingByCategory:
    """Test issue grouping by category."""
    
    @pytest.mark.asyncio
    async def test_groups_issues_by_category(
        self,
        verifier_service,
        state_service,
        mock_github_service,
        mock_claude_provider
    ):
        """Test that issues are grouped by category for efficient Claude calls."""
        pr_id = "test/repo/1"
        
        # Create issues with multiple categories
        from src.models.review import Severity
        issues = [
            OpenIssue(issue_id="a.py:1:security", category="security", filename="a.py", line=1, severity=Severity.CRITICAL, body="Issue 1"),
            OpenIssue(issue_id="b.py:2:security", category="security", filename="b.py", line=2, severity=Severity.CRITICAL, body="Issue 2"),
            OpenIssue(issue_id="c.py:3:maintainability", category="maintainability", filename="c.py", line=3, severity=Severity.MAJOR, body="Issue 3"),
        ]
        
        state_service.save(
            pr_id=pr_id,
            issues=issues,
            commit_sha="old_commit",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues"
        )
        
        mock_github_service.get_commit_diff.return_value = "diff..."
        
        # Mock Claude to return all fixed - one response per category
        mock_claude_provider.generate.side_effect = [
            # maintainability category
            """{"verifications": [{"issue_id": "c.py:3:maintainability", "is_fixed": true, "comment": "Fixed", "confidence": 0.9}]}""",
            # security category (2 issues)
            """{"verifications": [{"issue_id": "a.py:1:security", "is_fixed": true, "comment": "Fixed", "confidence": 0.9}, {"issue_id": "b.py:2:security", "is_fixed": true, "comment": "Fixed", "confidence": 0.9}]}"""
        ]
        
        await verifier_service.verify_fixes(
            owner="test",
            repo="repo",
            pull_number=1,
            new_commit_sha="new_commit"
        )
        
        # Claude should be called once per category (2 categories)
        assert mock_claude_provider.generate.call_count == 2


class TestStateUpdates:
    """Test state store updates."""
    
    @pytest.mark.asyncio
    async def test_updates_state_with_resolved_issues(
        self,
        verifier_service,
        state_service,
        mock_github_service,
        mock_claude_provider,
        sample_issues
    ):
        """Test that state store is updated with resolved issues."""
        pr_id = "test/repo/1"
        
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="old_commit",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues"
        )
        
        mock_github_service.get_commit_diff.return_value = "diff..."
        
        # Mock Claude - first issue fixed, others not
        mock_claude_provider.generate.side_effect = [
            # hardcoded_values - NOT fixed
            """{"verifications": [{"issue_id": "config.py:5:hardcoded_values", "is_fixed": false, "comment": "Not fixed", "confidence": 0.90}]}""",
            # maintainability - NOT fixed
            """{"verifications": [{"issue_id": "app.py:20:maintainability", "is_fixed": false, "comment": "Not fixed", "confidence": 0.85}]}""",
            # security - FIXED
            """{"verifications": [{"issue_id": "app.py:10:security", "is_fixed": true, "comment": "Fixed", "confidence": 0.95}]}"""
        ]
        
        await verifier_service.verify_fixes(
            owner="test",
            repo="repo",
            pull_number=1,
            new_commit_sha="new_commit"
        )
        
        # Load state and verify updates
        state = state_service.load(pr_id)
        
        # Check that first issue is marked resolved
        security_issue = next(i for i in state.all_issues if i.id == "app.py:10:security")
        assert security_issue.resolved is True
        
        # Check that other issues are still open
        maint_issue = next(i for i in state.all_issues if i.id == "app.py:20:maintainability")
        assert maint_issue.resolved is False
    
    @pytest.mark.asyncio
    async def test_increments_round_number(
        self,
        verifier_service,
        state_service,
        mock_github_service,
        mock_claude_provider,
        sample_issues
    ):
        """Test that round number is incremented."""
        pr_id = "test/repo/1"
        
        # Save initial state (round 1)
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="old_commit",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues",
            round_num=1
        )
        
        mock_github_service.get_commit_diff.return_value = "diff..."
        mock_claude_provider.generate.return_value = """
        {
          "verifications": [
            {"issue_id": "app.py:10:security", "is_fixed": true, "comment": "Fixed", "confidence": 0.95},
            {"issue_id": "app.py:20:maintainability", "is_fixed": true, "comment": "Fixed", "confidence": 0.90},
            {"issue_id": "config.py:5:hardcoded_values", "is_fixed": true, "comment": "Fixed", "confidence": 0.98}
          ]
        }
        """
        
        await verifier_service.verify_fixes(
            owner="test",
            repo="repo",
            pull_number=1,
            new_commit_sha="new_commit"
        )
        
        # Verify round was incremented
        state = state_service.load(pr_id)
        assert state.round == 2
    
    @pytest.mark.asyncio
    async def test_marks_pr_approved_when_all_fixed(
        self,
        verifier_service,
        state_service,
        mock_github_service,
        mock_claude_provider,
        sample_issues
    ):
        """Test that PR is marked approved when all issues are fixed."""
        pr_id = "test/repo/1"
        
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="old_commit",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues"
        )
        
        mock_github_service.get_commit_diff.return_value = "diff..."
        mock_claude_provider.generate.return_value = """
        {
          "verifications": [
            {"issue_id": "app.py:10:security", "is_fixed": true, "comment": "Fixed", "confidence": 0.95},
            {"issue_id": "app.py:20:maintainability", "is_fixed": true, "comment": "Fixed", "confidence": 0.90},
            {"issue_id": "config.py:5:hardcoded_values", "is_fixed": true, "comment": "Fixed", "confidence": 0.98}
          ]
        }
        """
        
        await verifier_service.verify_fixes(
            owner="test",
            repo="repo",
            pull_number=1,
            new_commit_sha="new_commit"
        )
        
        # Verify PR is marked approved
        state = state_service.load(pr_id)
        assert state.verdict == ReviewScore.APPROVE


class TestErrorHandling:
    """Test error handling."""
    
    @pytest.mark.asyncio
    async def test_handles_github_api_error(
        self,
        verifier_service,
        state_service,
        mock_github_service,
        sample_issues
    ):
        """Test that GitHub API errors are handled gracefully."""
        pr_id = "test/repo/1"
        
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="old_commit",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues"
        )
        
        # Mock GitHub to raise error
        mock_github_service.get_commit_diff.side_effect = Exception("GitHub API error")
        
        # Should raise exception
        with pytest.raises(Exception, match="GitHub API error"):
            await verifier_service.verify_fixes(
                owner="test",
                repo="repo",
                pull_number=1,
                new_commit_sha="new_commit"
            )
    
    @pytest.mark.asyncio
    async def test_handles_malformed_claude_response(
        self,
        verifier_service,
        state_service,
        mock_github_service,
        mock_claude_provider,
        sample_issues
    ):
        """Test that malformed Claude responses are handled gracefully."""
        pr_id = "test/repo/1"
        
        state_service.save(
            pr_id=pr_id,
            issues=sample_issues,
            commit_sha="old_commit",
            score=ReviewScore.REQUEST_CHANGES,
            summary="Found issues"
        )
        
        mock_github_service.get_commit_diff.return_value = "diff..."
        
        # Mock Claude to return invalid JSON
        mock_claude_provider.generate.return_value = "This is not JSON"
        
        # Should not crash - should assume issues not fixed
        result = await verifier_service.verify_fixes(
            owner="test",
            repo="repo",
            pull_number=1,
            new_commit_sha="new_commit"
        )
        
        # Should conservatively assume nothing was fixed
        assert result.fixed_issues == 0
