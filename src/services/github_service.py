import httpx
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GitHubService:
    def __init__(self):
        self.base_url = "https://api.github.com"
        self.token = settings.github_token
        logger.info(f"GitHubService initialized with base_url={self.base_url}")
    
    async def list_repos(self):
        logger.info("Fetching repository list")
        pass
    
    async def get_diff(self, owner: str, repo: str, pr_number: int):
        logger.info(f"Fetching diff for {owner}/{repo}#{pr_number}")
        pass
    
    async def post_review(self, owner: str, repo: str, pr_number: int, comments: list):
        logger.info(f"Posting review to {owner}/{repo}#{pr_number} with {len(comments)} comments")
        pass
