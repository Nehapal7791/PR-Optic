from anthropic import Anthropic
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ClaudeService:
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        logger.info("ClaudeService initialized with Anthropic client")
    
    async def build_prompt(self, diff: str) -> str:
        logger.debug(f"Building prompt for diff (length={len(diff)})")
        pass
    
    async def parse_response(self, response: str) -> list:
        logger.debug(f"Parsing Claude response (length={len(response)})")
        pass
