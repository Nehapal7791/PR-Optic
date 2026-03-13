from src.services.github_service import GitHubService
from src.services.claude_service import ClaudeService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ReviewService:
    def __init__(self):
        self.github = GitHubService()
        self.claude = ClaudeService()
        logger.info("ReviewService initialized")
    
    async def orchestrate_review(self, owner: str, repo: str, pr_number: int):
        logger.info(f"Starting review orchestration for {owner}/{repo}#{pr_number}")
        try:
            logger.debug("Review orchestration completed successfully")
            pass
        except Exception as e:
            logger.error(f"Review orchestration failed: {e}", exc_info=True)
            raise
