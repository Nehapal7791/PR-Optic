import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from src.services.github_service import GitHubService
from src.exceptions import GitHubServiceError
from src.models.github import PRFile, PullRequest


@pytest.fixture
def github_service():
    """Fixture to create GitHubService instance."""
    return GitHubService()


@pytest.fixture
def mock_pr_files_response():
    """Mock GitHub API response for PR files."""
    return [
        {
            "filename": "src/main.py",
            "status": "modified",
            "additions": 10,
            "deletions": 5,
            "changes": 15,
            "patch": "@@ -1,5 +1,10 @@\n+new line\n-old line",
            "sha": "abc123",
            "blob_url": "https://github.com/owner/repo/blob/abc123/src/main.py",
            "raw_url": "https://github.com/owner/repo/raw/abc123/src/main.py",
            "contents_url": "https://api.github.com/repos/owner/repo/contents/src/main.py"
        },
        {
            "filename": "image.png",
            "status": "added",
            "additions": 0,
            "deletions": 0,
            "changes": 0,
            "sha": "def456",
            "blob_url": "https://github.com/owner/repo/blob/def456/image.png",
            "raw_url": "https://github.com/owner/repo/raw/def456/image.png",
            "contents_url": "https://api.github.com/repos/owner/repo/contents/image.png"
        }
    ]


@pytest.fixture
def mock_pr_response():
    """Mock GitHub API response for PR details."""
    return {
        "number": 123,
        "title": "Test PR",
        "body": "Test description",
        "state": "open",
        "html_url": "https://github.com/owner/repo/pull/123",
        "head": {"sha": "head_sha_123"},
        "base": {"sha": "base_sha_456"},
        "user": {"login": "testuser"},
        "created_at": "2026-03-14T00:00:00Z",
        "updated_at": "2026-03-14T01:00:00Z"
    }


@pytest.fixture
def mock_repos_response():
    """Mock GitHub API response for repository list."""
    return [
        {
            "id": 1,
            "name": "test-repo",
            "full_name": "owner/test-repo",
            "private": False,
            "html_url": "https://github.com/owner/test-repo",
            "description": "Test repository",
            "owner": {"login": "owner"}
        }
    ]


class TestGitHubServiceInit:
    """Test GitHubService initialization."""
    
    def test_github_service_init(self, github_service):
        """Test service initializes with correct base URL and headers."""
        assert github_service.base_url == "https://api.github.com"
        assert "Authorization" in github_service.headers
        assert github_service.headers["Accept"] == "application/vnd.github+json"
        assert github_service.headers["X-GitHub-Api-Version"] == "2022-11-28"


class TestListRepos:
    """Test list_repos functionality."""
    
    @pytest.mark.asyncio
    async def test_list_repos_success(self, github_service, mock_repos_response):
        """Test successful repository listing."""
        with patch.object(github_service, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_repos_response
            
            repos = await github_service.list_repos()
            
            assert len(repos) == 1
            assert repos[0]["name"] == "test-repo"
            assert repos[0]["full_name"] == "owner/test-repo"
            mock_request.assert_called_once_with(
                method="GET",
                endpoint="/user/repos",
                params={"per_page": 30, "sort": "updated"}
            )
    
    @pytest.mark.asyncio
    async def test_list_repos_empty(self, github_service):
        """Test listing repos returns empty list when none exist."""
        with patch.object(github_service, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = []
            
            repos = await github_service.list_repos()
            
            assert repos == []
            assert isinstance(repos, list)
    
    @pytest.mark.asyncio
    async def test_list_repos_api_error(self, github_service):
        """Test list_repos raises GitHubServiceError on API failure."""
        with patch.object(github_service, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = GitHubServiceError("API Error", status_code=401)
            
            with pytest.raises(GitHubServiceError) as exc_info:
                await github_service.list_repos()
            
            assert exc_info.value.status_code == 401


class TestGetPRFiles:
    """Test get_pr_files functionality."""
    
    @pytest.mark.asyncio
    async def test_get_pr_files_success(self, github_service, mock_pr_files_response):
        """Test successful PR files retrieval."""
        with patch.object(github_service, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_pr_files_response
            
            files = await github_service.get_pr_files("owner", "repo", 123)
            
            assert len(files) == 2
            assert isinstance(files[0], PRFile)
            assert files[0].filename == "src/main.py"
            assert files[0].patch != ""
            assert files[0].additions == 10
            assert files[0].deletions == 5
            
            # Binary file should have empty patch
            assert files[1].filename == "image.png"
            assert files[1].patch == ""
            
            mock_request.assert_called_once_with(
                method="GET",
                endpoint="/repos/owner/repo/pulls/123/files"
            )
    
    @pytest.mark.asyncio
    async def test_get_pr_files_binary_files(self, github_service):
        """Test binary files return empty patch string."""
        binary_file_response = [{
            "filename": "binary.exe",
            "status": "added",
            "additions": 0,
            "deletions": 0,
            "changes": 0,
            "sha": "xyz789",
            "blob_url": "https://github.com/owner/repo/blob/xyz789/binary.exe",
            "raw_url": "https://github.com/owner/repo/raw/xyz789/binary.exe",
            "contents_url": "https://api.github.com/repos/owner/repo/contents/binary.exe"
        }]
        
        with patch.object(github_service, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = binary_file_response
            
            files = await github_service.get_pr_files("owner", "repo", 123)
            
            assert len(files) == 1
            assert files[0].patch == ""
    
    @pytest.mark.asyncio
    async def test_get_pr_files_not_found(self, github_service):
        """Test get_pr_files raises error for non-existent PR."""
        with patch.object(github_service, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = GitHubServiceError("Not Found", status_code=404)
            
            with pytest.raises(GitHubServiceError) as exc_info:
                await github_service.get_pr_files("owner", "repo", 999)
            
            assert exc_info.value.status_code == 404


class TestGetPRDetails:
    """Test get_pr_details functionality."""
    
    @pytest.mark.asyncio
    async def test_get_pr_details_success(self, github_service, mock_pr_response):
        """Test successful PR details retrieval."""
        with patch.object(github_service, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_pr_response.copy()
            
            pr = await github_service.get_pr_details("owner", "repo", 123)
            
            assert isinstance(pr, PullRequest)
            assert pr.number == 123
            assert pr.title == "Test PR"
            assert pr.state == "open"
            assert pr.head_sha == "head_sha_123"
            assert pr.base_sha == "base_sha_456"
            
            mock_request.assert_called_once_with(
                method="GET",
                endpoint="/repos/owner/repo/pulls/123"
            )


class TestPostReview:
    """Test post_review functionality."""
    
    @pytest.mark.asyncio
    async def test_post_review_comment_only(self, github_service):
        """Test posting review with comment only."""
        mock_response = {"id": 12345, "state": "COMMENTED"}
        
        with patch.object(github_service, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await github_service.post_review(
                owner="owner",
                repo="repo",
                pr_number=123,
                commit_sha="abc123",
                body="Great work!",
                event="COMMENT"
            )
            
            assert result["id"] == 12345
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args.kwargs["json_data"]["event"] == "COMMENT"
            assert call_args.kwargs["json_data"]["body"] == "Great work!"
    
    @pytest.mark.asyncio
    async def test_post_review_with_inline_comments(self, github_service):
        """Test posting review with inline comments."""
        mock_response = {"id": 12346, "state": "CHANGES_REQUESTED"}
        inline_comments = [
            {"path": "src/main.py", "position": 5, "body": "Fix this"}
        ]
        
        with patch.object(github_service, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await github_service.post_review(
                owner="owner",
                repo="repo",
                pr_number=123,
                commit_sha="abc123",
                body="Changes needed",
                event="REQUEST_CHANGES",
                comments=inline_comments
            )
            
            assert result["id"] == 12346
            call_args = mock_request.call_args
            assert call_args.kwargs["json_data"]["comments"] == inline_comments
    
    @pytest.mark.asyncio
    async def test_post_review_approve(self, github_service):
        """Test approving a PR."""
        mock_response = {"id": 12347, "state": "APPROVED"}
        
        with patch.object(github_service, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await github_service.post_review(
                owner="owner",
                repo="repo",
                pr_number=123,
                commit_sha="abc123",
                body="LGTM!",
                event="APPROVE"
            )
            
            assert result["state"] == "APPROVED"


class TestMakeRequest:
    """Test _make_request helper method."""
    
    @pytest.mark.asyncio
    async def test_make_request_timeout(self, github_service):
        """Test request timeout handling."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(
                side_effect=httpx.TimeoutException("Timeout")
            )
            
            with pytest.raises(GitHubServiceError) as exc_info:
                await github_service._make_request("GET", "/test")
            
            assert "timeout" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_make_request_network_error(self, github_service):
        """Test network error handling."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(
                side_effect=httpx.RequestError("Network error")
            )
            
            with pytest.raises(GitHubServiceError) as exc_info:
                await github_service._make_request("GET", "/test")
            
            assert "Request failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_make_request_401_unauthorized(self, github_service):
        """Test 401 unauthorized error."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"message": "Bad credentials"}
        mock_response.text = '{"message": "Bad credentials"}'
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(
                return_value=mock_response
            )
            
            with pytest.raises(GitHubServiceError) as exc_info:
                await github_service._make_request("GET", "/test")
            
            assert exc_info.value.status_code == 401
            assert "Bad credentials" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_make_request_404_not_found(self, github_service):
        """Test 404 not found error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Not Found"}
        mock_response.text = '{"message": "Not Found"}'
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(
                return_value=mock_response
            )
            
            with pytest.raises(GitHubServiceError) as exc_info:
                await github_service._make_request("GET", "/test")
            
            assert exc_info.value.status_code == 404
