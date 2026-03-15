import httpx
from src.config import settings
from src.utils.logger import get_logger
from src.models.github import PRFile, PullRequest, Repository
from src.exceptions import GitHubServiceError

logger = get_logger(__name__)


class GitHubService:
    def __init__(self):
        self.base_url = "https://api.github.com"
        self.token = settings.github_token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        logger.info(f"GitHubService initialized with base_url={self.base_url}")
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        json_data: dict | None = None,
        params: dict | None = None
    ) -> dict | list:
        """Make authenticated request to GitHub API."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=json_data,
                    params=params
                )
                
                if response.status_code >= 400:
                    error_detail = await response.aread()
                    error_text = error_detail.decode()
                    logger.error(f"GitHub API request failed: {error_text}")
                    
                    # Try to parse error message
                    try:
                        import json
                        error_json = json.loads(error_text)
                        error_msg = error_json.get('message', response.reason_phrase)
                        logger.error(f"GitHub error message: {error_msg}")
                    except:
                        error_msg = response.reason_phrase
                    
                    raise GitHubServiceError(
                        f"GitHub API error: {response.status_code} - {error_msg}"
                    )
                
                return response.json()
        
        except httpx.TimeoutException as e:
            logger.error(f"GitHub API request timeout: {e}")
            raise GitHubServiceError(f"Request timeout: {e}")
        except httpx.RequestError as e:
            logger.error(f"GitHub API request error: {e}")
            raise GitHubServiceError(f"Request failed: {e}")
    
    async def list_repos(self, per_page: int = 30) -> list[dict]:
        """List repositories accessible to the authenticated user."""
        logger.info("Fetching repository list")
        
        try:
            repos = await self._make_request(
                method="GET",
                endpoint="/user/repos",
                params={"per_page": per_page, "sort": "updated"}
            )
            
            logger.info(f"Fetched {len(repos)} repositories")
            return repos
        
        except GitHubServiceError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing repos: {e}", exc_info=True)
            raise GitHubServiceError(f"Failed to list repositories: {e}")
    
    async def get_pr_details(self, owner: str, repo: str, pr_number: int) -> PullRequest:
        """Get pull request details."""
        logger.info(f"Fetching PR details for {owner}/{repo}#{pr_number}")
        
        try:
            pr_data = await self._make_request(
                method="GET",
                endpoint=f"/repos/{owner}/{repo}/pulls/{pr_number}"
            )
            
            # Extract head and base SHA from nested objects
            pr_data["head"] = pr_data["head"]["sha"]
            pr_data["base"] = pr_data["base"]["sha"]
            
            pr = PullRequest(**pr_data)
            logger.info(f"Fetched PR #{pr.number}: {pr.title}")
            return pr
        
        except GitHubServiceError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting PR details: {e}", exc_info=True)
            raise GitHubServiceError(f"Failed to get PR details: {e}")
    
    async def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[PRFile]:
        """Get list of files changed in a pull request."""
        logger.info(f"Fetching files for {owner}/{repo}#{pr_number}")
        
        try:
            files_data = await self._make_request(
                method="GET",
                endpoint=f"/repos/{owner}/{repo}/pulls/{pr_number}/files"
            )
            
            pr_files = []
            for file_data in files_data:
                # Binary files don't have patch
                if "patch" not in file_data:
                    file_data["patch"] = ""
                    logger.debug(f"Binary file detected: {file_data['filename']}")
                
                pr_file = PRFile(**file_data)
                pr_files.append(pr_file)
            
            logger.info(f"Fetched {len(pr_files)} files for PR #{pr_number}")
            return pr_files
        
        except GitHubServiceError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting PR files: {e}", exc_info=True)
            raise GitHubServiceError(f"Failed to get PR files: {e}")
    
    async def post_review(
        self, 
        owner: str, 
        repo: str, 
        pr_number: int, 
        commit_sha: str,
        body: str,
        event: str = "COMMENT",
        comments: list[dict] | None = None
    ) -> dict:
        """Post a review on a pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            commit_sha: SHA of the commit to review
            body: Main review body text
            event: Review event type (APPROVE, REQUEST_CHANGES, COMMENT)
            comments: List of inline comments with path, position, body
        
        Returns:
            Review response from GitHub API
        """
        logger.info(
            f"Posting review to {owner}/{repo}#{pr_number} "
            f"(event={event}, comments={len(comments) if comments else 0})"
        )
        
        review_data = {
            "commit_id": commit_sha,
            "body": body,
            "event": event
        }
        
        if comments:
            review_data["comments"] = comments
        
        try:
            logger.debug(f"Review payload: {review_data}")
            response = await self._make_request(
                method="POST",
                endpoint=f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                json_data=review_data
            )
            
            logger.info(f"Successfully posted review (id={response.get('id')})")
            return response
        
        except GitHubServiceError as e:
            logger.error("GitHub API rejected review. This commonly happens if:")
            logger.error("  1. You're trying to review your own PR (GitHub doesn't allow this)")
            logger.error("  2. Invalid line numbers in comments (lines not in diff)")
            logger.error("  3. Duplicate review on same commit SHA")
            logger.error(f"Review data: commit={commit_sha[:8]}, event={event}, comments={len(comments) if comments else 0}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error posting review: {e}", exc_info=True)
            raise GitHubServiceError(f"Failed to post review: {e}")
    
    async def post_pr_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
        path: str,
        line: int,
        body: str,
        side: str = "RIGHT"
    ) -> dict:
        """Post an individual inline comment on a PR.
        
        This posts a single comment on a specific line, similar to how
        developers comment during code review.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            commit_sha: SHA of the commit
            path: File path
            line: Line number
            body: Comment body
            side: Which side of diff (RIGHT for new, LEFT for old)
        
        Returns:
            Comment response from GitHub API
        """
        comment_data = {
            "body": body,
            "commit_id": commit_sha,
            "path": path,
            "line": line,
            "side": side
        }
        
        try:
            response = await self._make_request(
                method="POST",
                endpoint=f"/repos/{owner}/{repo}/pulls/{pr_number}/comments",
                json_data=comment_data
            )
            logger.debug(f"Posted comment on {path}:{line}")
            return response
        except GitHubServiceError:
            raise
        except Exception as e:
            logger.error(f"Failed to post PR comment: {e}", exc_info=True)
            raise GitHubServiceError(f"Failed to post PR comment: {e}")
