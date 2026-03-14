from fastapi import APIRouter, HTTPException, Query
from src.utils.logger import get_logger
from src.services.github_service import GitHubService
from src.exceptions import GitHubServiceError

logger = get_logger(__name__)

router = APIRouter(tags=["github"])


@router.get("/repos")
async def list_repos(per_page: int = Query(default=30, le=100)):
    """List repositories accessible to the authenticated user.
    
    Args:
        per_page: Number of repos per page (max 100)
    
    Returns:
        JSON array of repositories
    
    Raises:
        401: Invalid GitHub token
        500: Server error
    """
    logger.info(f"GET /api/repos - Listing repositories (per_page={per_page})")
    
    try:
        service = GitHubService()
        repos = await service.list_repos(per_page=per_page)
        
        logger.info(f"Successfully fetched {len(repos)} repositories")
        return {
            "count": len(repos),
            "repos": repos
        }
    
    except GitHubServiceError as e:
        logger.error(f"GitHub API error: {e}")
        if e.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="Invalid GitHub token. Please check your GITHUB_TOKEN in .env"
            )
        raise HTTPException(
            status_code=e.status_code or 500,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/repos/{owner}/{repo}/pulls")
async def list_pull_requests(
    owner: str,
    repo: str,
    state: str = Query(default="open", regex="^(open|closed|all)$")
):
    """List pull requests for a repository.
    
    Args:
        owner: Repository owner
        repo: Repository name
        state: PR state filter (open, closed, all)
    
    Returns:
        JSON array of pull requests
    
    Raises:
        404: Repository not found
        401: Invalid GitHub token
        500: Server error
    """
    logger.info(f"GET /api/repos/{owner}/{repo}/pulls - Listing PRs (state={state})")
    
    try:
        service = GitHubService()
        
        # GitHub API endpoint for listing PRs
        prs = await service._make_request(
            method="GET",
            endpoint=f"/repos/{owner}/{repo}/pulls",
            params={"state": state, "per_page": 30}
        )
        
        logger.info(f"Successfully fetched {len(prs)} pull requests")
        return {
            "count": len(prs),
            "owner": owner,
            "repo": repo,
            "state": state,
            "pulls": prs
        }
    
    except GitHubServiceError as e:
        logger.error(f"GitHub API error: {e}")
        if e.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Repository {owner}/{repo} not found"
            )
        elif e.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="Invalid GitHub token. Please check your GITHUB_TOKEN in .env"
            )
        raise HTTPException(
            status_code=e.status_code or 500,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/repos/{owner}/{repo}/pulls/{pr_number}/files")
async def get_pull_request_files(owner: str, repo: str, pr_number: int):
    """Get files changed in a pull request.
    
    Args:
        owner: Repository owner
        repo: Repository name
        pr_number: Pull request number
    
    Returns:
        JSON array of changed files with patches
    
    Raises:
        404: PR not found
        401: Invalid GitHub token
        500: Server error
    """
    logger.info(f"GET /api/repos/{owner}/{repo}/pulls/{pr_number}/files")
    
    try:
        service = GitHubService()
        files = await service.get_pr_files(owner, repo, pr_number)
        
        logger.info(f"Successfully fetched {len(files)} files for PR #{pr_number}")
        return {
            "count": len(files),
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "files": [
                {
                    "filename": f.filename,
                    "status": f.status,
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "changes": f.changes,
                    "patch": f.patch,
                    "sha": f.sha,
                    "blob_url": f.blob_url
                }
                for f in files
            ]
        }
    
    except GitHubServiceError as e:
        logger.error(f"GitHub API error: {e}")
        if e.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Pull request #{pr_number} not found in {owner}/{repo}"
            )
        elif e.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="Invalid GitHub token. Please check your GITHUB_TOKEN in .env"
            )
        raise HTTPException(
            status_code=e.status_code or 500,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
