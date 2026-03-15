"""Tests for dashboard API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
from src.api.routes.reviews import router
from src.models.dashboard import ReviewResponse, PRStatus
from src.models.review import ReviewResult, ReviewScore, ReviewComment, Severity
from src.models.state import PRReviewState, OpenIssue
from src.models.github import PullRequest
from src.services.github_service import GitHubServiceError


@pytest.fixture
def app():
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_review_request():
    """Sample review request."""
    return {
        "owner": "testuser",
        "repo": "testrepo",
        "pull_number": 1
    }


@pytest.fixture
def sample_pr():
    """Sample PR details."""
    return PullRequest(
        number=1,
        title="Test PR",
        body="Test description",
        state="open",
        user={"login": "testuser"},
        head_sha="abc123def456",
        base_sha="main123",
        html_url="https://github.com/test/repo/pull/1",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z"
    )


@pytest.fixture
def sample_review_result():
    """Sample review result."""
    return ReviewResult(
        score=ReviewScore.REQUEST_CHANGES,
        summary="Found 3 issues",
        comments=[
            ReviewComment(
                filename="test.py",
                line=10,
                body="Test issue 1",
                category="security",
                severity=Severity.CRITICAL
            ),
            ReviewComment(
                filename="test.py",
                line=20,
                body="Test issue 2",
                category="hardcoded_values",
                severity=Severity.MAJOR
            ),
            ReviewComment(
                filename="app.py",
                line=5,
                body="Test issue 3",
                category="maintainability",
                severity=Severity.MINOR
            )
        ]
    )


@pytest.fixture
def sample_pr_state():
    """Sample PR state."""
    return PRReviewState(
        pr_id="testuser/testrepo/1",
        last_reviewed_commit="abc123def456",
        open_issues=[
            OpenIssue(
                issue_id="test.py:10:security",
                filename="test.py",
                line=10,
                category="security",
                severity=Severity.CRITICAL,
                body="SQL injection vulnerability",
                suggested_fix="Use parameterized queries"
            ),
            OpenIssue(
                issue_id="test.py:20:performance",
                filename="test.py",
                line=20,
                category="performance",
                severity=Severity.MAJOR,
                body="Inefficient loop"
            )
        ],
        last_review_score=ReviewScore.REQUEST_CHANGES,
        last_review_summary="Found 2 critical issues"
    )


class TestManualReviewEndpoint:
    """Test POST /api/reviews endpoint."""
    
    @pytest.mark.asyncio
    async def test_trigger_review_success(self, client, sample_review_request, sample_pr, sample_review_result):
        """Test successful manual review trigger."""
        with patch('src.api.routes.reviews.GitHubService') as mock_github_cls, \
             patch('src.api.routes.reviews.ReviewOrchestrator') as mock_orch_cls:
            
            # Mock GitHub service
            mock_github = AsyncMock()
            mock_github.get_pr_details.return_value = sample_pr
            mock_github_cls.return_value = mock_github
            
            # Mock orchestrator
            mock_orch = AsyncMock()
            mock_orch.orchestrate.return_value = sample_review_result
            mock_orch_cls.return_value = mock_orch
            
            response = client.post("/api/reviews", json=sample_review_request)
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["pr_id"] == "testuser/testrepo/1"
            assert data["score"] == "request_changes"
            assert data["comments"] == 3
            assert "processing_time" in data
            
            # Verify orchestrate was called with post_to_github=False
            mock_orch.orchestrate.assert_called_once()
            call_kwargs = mock_orch.orchestrate.call_args.kwargs
            assert call_kwargs["post_to_github"] is False
    
    def test_trigger_review_missing_fields(self, client):
        """Test review trigger with missing required fields."""
        # Missing pull_number
        response = client.post("/api/reviews", json={
            "owner": "testuser",
            "repo": "testrepo"
        })
        
        assert response.status_code == 422
    
    def test_trigger_review_invalid_pull_number(self, client):
        """Test review trigger with invalid pull_number."""
        response = client.post("/api/reviews", json={
            "owner": "testuser",
            "repo": "testrepo",
            "pull_number": 0  # Must be > 0
        })
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_trigger_review_pr_not_found(self, client, sample_review_request):
        """Test review trigger when PR does not exist."""
        with patch('src.api.routes.reviews.GitHubService') as mock_github_cls:
            mock_github = AsyncMock()
            mock_github.get_pr_details.side_effect = GitHubServiceError("PR not found")
            mock_github_cls.return_value = mock_github
            
            response = client.post("/api/reviews", json=sample_review_request)
            
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_trigger_review_processing_error(self, client, sample_review_request, sample_pr):
        """Test review trigger when processing fails."""
        with patch('src.api.routes.reviews.GitHubService') as mock_github_cls, \
             patch('src.api.routes.reviews.ReviewOrchestrator') as mock_orch_cls:
            
            mock_github = AsyncMock()
            mock_github.get_pr_details.return_value = sample_pr
            mock_github_cls.return_value = mock_github
            
            mock_orch = AsyncMock()
            mock_orch.orchestrate.side_effect = Exception("AI service error")
            mock_orch_cls.return_value = mock_orch
            
            response = client.post("/api/reviews", json=sample_review_request)
            
            assert response.status_code == 500
            assert "failed" in response.json()["detail"].lower()
    
    def test_trigger_review_empty_owner(self, client):
        """Test review trigger with empty owner."""
        response = client.post("/api/reviews", json={
            "owner": "",
            "repo": "testrepo",
            "pull_number": 1
        })
        
        assert response.status_code == 422
    
    def test_trigger_review_empty_repo(self, client):
        """Test review trigger with empty repo."""
        response = client.post("/api/reviews", json={
            "owner": "testuser",
            "repo": "",
            "pull_number": 1
        })
        
        assert response.status_code == 422


class TestPRStatusEndpoint:
    """Test GET /api/reviews/{owner}/{repo}/{pr}/status endpoint."""
    
    def test_get_status_success(self, client, sample_pr_state):
        """Test successful status retrieval."""
        with patch('src.api.routes.reviews.StateService') as mock_state_cls:
            mock_state_service = MagicMock()
            mock_state_service.load.return_value = sample_pr_state
            mock_state_cls.return_value = mock_state_service
            
            response = client.get("/api/reviews/testuser/testrepo/1/status")
            
            assert response.status_code == 200
            data = response.json()
            assert data["pr_id"] == "testuser/testrepo/1"
            assert data["commit_sha"] == "abc123def456"
            assert data["round"] == 1
            assert data["verdict"] == "request_changes"
            assert len(data["open_issues"]) == 2
            assert data["open_issues"][0]["filename"] == "test.py"
            assert data["open_issues"][0]["line"] == 10
            assert data["open_issues"][0]["severity"] == "critical"
            assert data["open_issues"][0]["is_resolved"] is False
    
    def test_get_status_pr_not_reviewed(self, client):
        """Test status retrieval when PR has not been reviewed."""
        with patch('src.api.routes.reviews.StateService') as mock_state_cls:
            mock_state_service = MagicMock()
            mock_state_service.load.return_value = None
            mock_state_cls.return_value = mock_state_service
            
            response = client.get("/api/reviews/testuser/testrepo/1/status")
            
            assert response.status_code == 404
            assert "not been reviewed" in response.json()["detail"]
    
    def test_get_status_service_error(self, client):
        """Test status retrieval when service fails."""
        with patch('src.api.routes.reviews.StateService') as mock_state_cls:
            mock_state_service = MagicMock()
            mock_state_service.load.side_effect = Exception("Database error")
            mock_state_cls.return_value = mock_state_service
            
            response = client.get("/api/reviews/testuser/testrepo/1/status")
            
            assert response.status_code == 500
            assert "failed" in response.json()["detail"].lower()
    
    def test_get_status_no_open_issues(self, client):
        """Test status retrieval when PR has no open issues."""
        state_with_no_issues = PRReviewState(
            pr_id="testuser/testrepo/1",
            last_reviewed_commit="abc123",
            open_issues=[],
            last_review_score=ReviewScore.APPROVE,
            last_review_summary="All good!"
        )
        
        with patch('src.api.routes.reviews.StateService') as mock_state_cls:
            mock_state_service = MagicMock()
            mock_state_service.load.return_value = state_with_no_issues
            mock_state_cls.return_value = mock_state_service
            
            response = client.get("/api/reviews/testuser/testrepo/1/status")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data["open_issues"]) == 0
            assert data["verdict"] == "approve"


class TestResponseModels:
    """Test response model validation."""
    
    def test_review_response_model(self):
        """Test ReviewResponse model validation."""
        response = ReviewResponse(
            status="success",
            pr_id="owner/repo/1",
            score=ReviewScore.REQUEST_CHANGES,
            comments=5,
            summary="Test summary",
            processing_time=12.5
        )
        
        assert response.status == "success"
        assert response.comments == 5
        assert response.processing_time == 12.5
    
    def test_pr_status_model(self, sample_pr_state):
        """Test PRStatus model validation."""
        from src.models.dashboard import IssueStatus
        
        open_issues = [
            IssueStatus(
                issue_id=issue.issue_id,
                filename=issue.filename,
                line=issue.line,
                category=issue.category,
                severity=issue.severity,
                body=issue.body,
                suggested_fix=issue.suggested_fix,
                created_at=issue.created_at,
                is_resolved=False
            )
            for issue in sample_pr_state.open_issues
        ]
        
        status = PRStatus(
            pr_id="owner/repo/1",
            commit_sha="abc123",
            round=1,
            verdict=ReviewScore.REQUEST_CHANGES,
            summary="Test summary",
            open_issues=open_issues,
            resolved_issues=[],
            last_updated=sample_pr_state.updated_at
        )
        
        assert status.pr_id == "owner/repo/1"
        assert len(status.open_issues) == 2
        assert status.round == 1
