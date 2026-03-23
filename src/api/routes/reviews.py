from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel
from src.services.review_orchestrator import ReviewOrchestrator
from src.services.github_service import GitHubService
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["reviews"])


class ReviewRequest(BaseModel):
    """Request body for manual PR review."""
    owner: str
    repo: str
    pull_number: int
    commit_sha: str | None = None
    post_to_github: bool = False


@router.post("/reviews")
async def trigger_review(
    request: ReviewRequest,
    background_tasks: BackgroundTasks,
    post_to_github: bool = Query(False),
):
    """Trigger a manual PR review.
    
    Args:
        request: Review request with PR details
        background_tasks: FastAPI background tasks
        
    Returns:
        Status message
    """
    effective_post_to_github = post_to_github or request.post_to_github

    logger.info(
        f"POST /api/reviews - Manual review triggered for {request.owner}/{request.repo}#{request.pull_number}, "
        f"post_to_github={effective_post_to_github}"
    )
    
    try:
        commit_sha = request.commit_sha
        if not commit_sha:
            pr = await GitHubService().get_pr_details(
                owner=request.owner,
                repo=request.repo,
                pr_number=request.pull_number,
            )
            commit_sha = pr.head_sha

        orchestrator = ReviewOrchestrator()

        # Run review in background
        background_tasks.add_task(
            orchestrator.orchestrate,
            owner=request.owner,
            repo=request.repo,
            pull_number=request.pull_number,
            commit_sha=commit_sha,
            post_to_github=effective_post_to_github,
        )
        return {
            "status": "triggered",
            "pr": f"{request.owner}/{request.repo}#{request.pull_number}",
            "post_to_github": effective_post_to_github,
            "commit_sha": commit_sha,
        }
        
    except Exception as e:
        logger.error(f"Failed to trigger review: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
