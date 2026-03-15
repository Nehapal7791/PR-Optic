"""
Tests for Review Orchestrator
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from src.services.review_orchestrator import ReviewOrchestrator
from src.models.github import PRFile, PullRequest
from src.models.review import ReviewResult, ReviewScore, TriageResult, ConcernCategory, ReviewComment, Severity
from src.models.state import PRReviewState, OpenIssue, VerificationResult


@pytest.fixture
def mock_github():
    """Mock GitHub service."""
    github = MagicMock()
    github.get_pr_details = AsyncMock()
    github.get_pr_files = AsyncMock()
    github.post_review = AsyncMock()
    return github


@pytest.fixture
def mock_ai():
    """Mock AI service."""
    ai = MagicMock()
    ai._provider = MagicMock()
    ai._provider.provider_name = "test_provider"
    ai.triage_diff = AsyncMock()
    ai.review_pull_request = AsyncMock()
    return ai


@pytest.fixture
def mock_state():
    """Mock state service."""
    state = MagicMock()
    state.load = MagicMock(return_value=None)
    state.save = MagicMock()
    state.clear = MagicMock()
    return state


@pytest.fixture
def orchestrator(mock_github, mock_ai, mock_state):
    """Create orchestrator with mocked dependencies."""
    return ReviewOrchestrator(
        github_service=mock_github,
        ai_service=mock_ai,
        state_service=mock_state
    )


@pytest.fixture
def sample_pr():
    """Sample PR data."""
    return PullRequest(
        number=1,
        title="Test PR",
        body="Test description",
        state="open",
        user={"login": "testuser"},
        head_sha="abc123",
        base_sha="main123",
        html_url="https://github.com/test/repo/pull/1",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z"
    )


@pytest.fixture
def sample_files():
    """Sample PR files."""
    return [
        PRFile(
            filename="src/test.py",
            status="modified",
            additions=10,
            deletions=5,
            changes=15,
            sha="abc123",
            patch="@@ -1,5 +1,10 @@\n+new code",
            blob_url="https://github.com/owner/repo/blob/abc123/src/test.py",
            raw_url="https://github.com/owner/repo/raw/abc123/src/test.py",
            contents_url="https://api.github.com/repos/owner/repo/contents/src/test.py"
        )
    ]


class TestOrchestration:
    """Test main orchestration routing."""
    
    @pytest.mark.asyncio
    async def test_orchestrate_new_pr_routes_to_run_review(
        self, orchestrator, mock_github, mock_ai, mock_state, sample_pr, sample_files
    ):
        """Test that new PR routes to run_review."""
        # Setup
        mock_state.load.return_value = None  # No existing state
        mock_github.get_pr_details.return_value = sample_pr
        mock_github.get_pr_files.return_value = sample_files
        
        mock_ai.triage_diff.return_value = TriageResult(
            categories=[],
            reasoning="No issues"
        )
        mock_ai.review_pull_request.return_value = ReviewResult(
            summary="Looks good",
            score=ReviewScore.APPROVE,
            comments=[],
            categories_reviewed=[]
        )
        
        # Execute
        result = await orchestrator.orchestrate(
            owner="test",
            repo="repo",
            pull_number=1,
            commit_sha="abc123",
            post_to_github=False
        )
        
        # Verify
        assert isinstance(result, ReviewResult)
        assert result.score == ReviewScore.APPROVE
        mock_state.load.assert_called_once_with("test/repo/1")
        mock_state.save.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_orchestrate_pr_with_open_issues_routes_to_verify_fixes(
        self, orchestrator, mock_github, mock_state, sample_files
    ):
        """Test that PR with open issues routes to verify_fixes."""
        # Setup existing state with open issues
        existing_state = PRReviewState(
            pr_id="test/repo/1",
            last_reviewed_commit="old123",
            open_issues=[
                OpenIssue(
                    issue_id="src/test.py:10:security",
                    filename="src/test.py",
                    line=10,
                    category="security",
                    severity=Severity.CRITICAL,
                    body="Security issue"
                )
            ],
            last_review_score=ReviewScore.REQUEST_CHANGES,
            last_review_summary="Issues found"
        )
        mock_state.load.return_value = existing_state
        mock_github.get_pr_files.return_value = sample_files
        
        # Execute
        result = await orchestrator.orchestrate(
            owner="test",
            repo="repo",
            pull_number=1,
            commit_sha="new123",
            post_to_github=False
        )
        
        # Verify
        assert isinstance(result, VerificationResult)
        assert result.total_issues == 1
        mock_state.load.assert_called_once_with("test/repo/1")


class TestRunReview:
    """Test run_review functionality."""
    
    @pytest.mark.asyncio
    async def test_run_review_empty_files_returns_early(
        self, orchestrator, mock_github, mock_ai, sample_pr
    ):
        """Test early return when no files changed."""
        mock_github.get_pr_details.return_value = sample_pr
        mock_github.get_pr_files.return_value = []
        
        result = await orchestrator.run_review(
            owner="test",
            repo="repo",
            pull_number=1,
            commit_sha="abc123",
            post_to_github=False
        )
        
        assert result.score == ReviewScore.APPROVE
        assert "No files changed" in result.summary
        mock_ai.triage_diff.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_run_review_filters_generated_files(
        self, orchestrator, mock_github, mock_ai, sample_pr
    ):
        """Test that generated files are filtered out."""
        mock_github.get_pr_details.return_value = sample_pr
        mock_github.get_pr_files.return_value = [
            PRFile(
                filename="package-lock.json",
                status="modified",
                additions=1000,
                deletions=500,
                changes=1500,
                sha="abc123",
                patch="...",
                blob_url="https://github.com/owner/repo/blob/abc123/package-lock.json",
                raw_url="https://github.com/owner/repo/raw/abc123/package-lock.json",
                contents_url="https://api.github.com/repos/owner/repo/contents/package-lock.json"
            )
        ]
        
        result = await orchestrator.run_review(
            owner="test",
            repo="repo",
            pull_number=1,
            commit_sha="abc123",
            post_to_github=False
        )
        
        assert result.score == ReviewScore.APPROVE
        assert "No reviewable files" in result.summary
        mock_ai.triage_diff.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_run_review_full_pipeline(
        self, orchestrator, mock_github, mock_ai, mock_state, sample_pr, sample_files
    ):
        """Test full review pipeline."""
        # Setup
        mock_github.get_pr_details.return_value = sample_pr
        mock_github.get_pr_files.return_value = sample_files
        
        mock_ai.triage_diff.return_value = TriageResult(
            categories=[ConcernCategory.SECURITY],
            reasoning="Found security issue"
        )
        
        mock_ai.review_pull_request.return_value = ReviewResult(
            summary="Security issue found",
            score=ReviewScore.REQUEST_CHANGES,
            comments=[
                ReviewComment(
                    filename="src/test.py",
                    line=10,
                    category=ConcernCategory.SECURITY,
                    severity=Severity.CRITICAL,
                    body="SQL injection vulnerability",
                    suggested_fix="Use parameterized queries"
                )
            ],
            categories_reviewed=[ConcernCategory.SECURITY]
        )
        
        # Execute
        result = await orchestrator.run_review(
            owner="test",
            repo="repo",
            pull_number=1,
            commit_sha="abc123",
            post_to_github=False
        )
        
        # Verify
        assert result.score == ReviewScore.REQUEST_CHANGES
        assert len(result.comments) == 1
        mock_ai.triage_diff.assert_called_once()
        mock_ai.review_pull_request.assert_called_once()
        mock_state.save.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_review_posts_to_github_when_enabled(
        self, orchestrator, mock_github, mock_ai, mock_state, sample_pr, sample_files
    ):
        """Test that review is posted to GitHub when post_to_github=True."""
        # Setup
        mock_github.get_pr_details.return_value = sample_pr
        mock_github.get_pr_files.return_value = sample_files
        
        mock_ai.triage_diff.return_value = TriageResult(
            categories=[ConcernCategory.SECURITY],
            reasoning="Found issue"
        )
        
        mock_ai.review_pull_request.return_value = ReviewResult(
            summary="Issue found",
            score=ReviewScore.COMMENT,
            comments=[
                ReviewComment(
                    filename="src/test.py",
                    line=10,
                    category=ConcernCategory.SECURITY,
                    severity=Severity.MAJOR,
                    body="Issue"
                )
            ],
            categories_reviewed=[ConcernCategory.SECURITY]
        )
        
        # Execute
        await orchestrator.run_review(
            owner="test",
            repo="repo",
            pull_number=1,
            commit_sha="abc123",
            post_to_github=True
        )
        
        # Verify
        mock_github.post_review.assert_called_once()
        call_args = mock_github.post_review.call_args
        assert call_args.kwargs["owner"] == "test"
        assert call_args.kwargs["repo"] == "repo"
        assert call_args.kwargs["pr_number"] == 1
        assert call_args.kwargs["event"] == "COMMENT"
    
    @pytest.mark.asyncio
    async def test_run_review_handles_errors_gracefully(
        self, orchestrator, mock_github, mock_ai, sample_pr, sample_files
    ):
        """Test that errors are handled gracefully."""
        mock_github.get_pr_details.return_value = sample_pr
        mock_github.get_pr_files.return_value = sample_files
        mock_ai.triage_diff.side_effect = Exception("AI service error")
        
        result = await orchestrator.run_review(
            owner="test",
            repo="repo",
            pull_number=1,
            commit_sha="abc123",
            post_to_github=False
        )
        
        assert result.score == ReviewScore.COMMENT
        assert "Review failed" in result.summary
        assert len(result.comments) == 0


class TestVerifyFixes:
    """Test verify_fixes functionality."""
    
    @pytest.mark.asyncio
    async def test_verify_fixes_all_fixed(
        self, orchestrator, mock_github, mock_state, sample_files
    ):
        """Test verification when all issues are fixed."""
        # Setup existing state
        existing_state = PRReviewState(
            pr_id="test/repo/1",
            last_reviewed_commit="old123",
            open_issues=[
                OpenIssue(
                    issue_id="src/test.py:10:security",
                    filename="src/test.py",
                    line=10,
                    category="security",
                    severity=Severity.CRITICAL,
                    body="Security issue"
                )
            ],
            last_review_score=ReviewScore.REQUEST_CHANGES,
            last_review_summary="Issues found"
        )
        
        # File was modified (line 10 in patch)
        modified_files = [
            PRFile(
                filename="src/test.py",
                status="modified",
                additions=5,
                deletions=2,
                changes=7,
                sha="new123",
                patch="@@ -8,3 +8,5 @@\n line 8\n line 9\n+line 10 fixed\n",
                blob_url="https://github.com/owner/repo/blob/new123/src/test.py",
                raw_url="https://github.com/owner/repo/raw/new123/src/test.py",
                contents_url="https://api.github.com/repos/owner/repo/contents/src/test.py"
            )
        ]
        
        mock_github.get_pr_files.return_value = modified_files
        
        # Execute
        result = await orchestrator.verify_fixes(
            owner="test",
            repo="repo",
            pull_number=1,
            commit_sha="new123",
            existing_state=existing_state,
            post_to_github=False
        )
        
        # Verify
        assert result.total_issues == 1
        assert result.fixed_issues == 1
        assert result.all_fixed is True
        mock_state.clear.assert_called_once_with("test/repo/1")
    
    @pytest.mark.asyncio
    async def test_verify_fixes_file_removed(
        self, orchestrator, mock_github, mock_state
    ):
        """Test verification when problematic file is removed."""
        existing_state = PRReviewState(
            pr_id="test/repo/1",
            last_reviewed_commit="old123",
            open_issues=[
                OpenIssue(
                    issue_id="src/removed.py:10:security",
                    filename="src/removed.py",
                    line=10,
                    category="security",
                    severity=Severity.CRITICAL,
                    body="Security issue"
                )
            ],
            last_review_score=ReviewScore.REQUEST_CHANGES,
            last_review_summary="Issues found"
        )
        
        # File not in PR anymore
        mock_github.get_pr_files.return_value = []
        
        result = await orchestrator.verify_fixes(
            owner="test",
            repo="repo",
            pull_number=1,
            commit_sha="new123",
            existing_state=existing_state,
            post_to_github=False
        )
        
        assert result.fixed_issues == 1
        assert result.all_fixed is True
        assert "File no longer present" in result.verifications[0].verification_comment


class TestFileFiltering:
    """Test file filtering logic."""
    
    def test_filter_files_removes_generated(self, orchestrator):
        """Test that generated files are filtered out."""
        files = [
            PRFile(
                filename="package-lock.json",
                status="modified",
                additions=100,
                deletions=50,
                changes=150,
                sha="abc123",
                patch="...",
                blob_url="url",
                raw_url="url",
                contents_url="url"
            ),
            PRFile(
                filename="src/code.py",
                status="modified",
                additions=10,
                deletions=5,
                changes=15,
                sha="def456",
                patch="...",
                blob_url="url",
                raw_url="url",
                contents_url="url"
            )
        ]
        
        filtered = orchestrator._filter_files(files)
        
        assert len(filtered) == 1
        assert filtered[0].filename == "src/code.py"
    
    def test_filter_files_removes_large(self, orchestrator):
        """Test that very large files are filtered out."""
        files = [
            PRFile(
                filename="large.py",
                status="modified",
                additions=600,
                deletions=100,
                changes=700,
                sha="abc123",
                patch="...",
                blob_url="url",
                raw_url="url",
                contents_url="url"
            ),
            PRFile(
                filename="small.py",
                status="modified",
                additions=10,
                deletions=5,
                changes=15,
                sha="def456",
                patch="...",
                blob_url="url",
                raw_url="url",
                contents_url="url"
            )
        ]
        
        filtered = orchestrator._filter_files(files)
        
        assert len(filtered) == 1
        assert filtered[0].filename == "small.py"
