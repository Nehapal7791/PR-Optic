"""
Claude Service (Backward Compatibility Wrapper)

This module maintains backward compatibility with existing code.
It now delegates to the AI service factory which supports multiple providers.

For new code, use: from src.services.ai_service_factory import get_ai_service
"""

from src.services.ai_service_factory import get_ai_service
from src.utils.logger import get_logger
from src.models.github import PRFile
from src.models.review import TriageResult, ReviewResult, ConcernCategory

logger = get_logger(__name__)


class ClaudeService:
    """Backward compatibility wrapper that delegates to AI service factory."""
    
    def __init__(self):
        self._provider = get_ai_service()
        logger.info(f"ClaudeService wrapper initialized with provider: {self._provider.provider_name}")
    
    @property
    def max_tokens(self) -> int:
        """Get max tokens from underlying provider."""
        return self._provider.max_tokens
    
    @property
    def client(self):
        """Provide client attribute for backward compatibility."""
        return getattr(self._provider, 'client', None)
    
    async def triage_diff(
        self,
        files: list[PRFile],
        pr_title: str,
        pr_body: str | None
    ) -> TriageResult:
        """Delegate to underlying provider."""
        return await self._provider.triage_diff(files, pr_title, pr_body)
    
    async def review_pull_request(
        self,
        files: list[PRFile],
        pr_title: str,
        pr_body: str | None,
        categories: list[ConcernCategory]
    ) -> ReviewResult:
        """Delegate to underlying provider."""
        return await self._provider.review_pull_request(files, pr_title, pr_body, categories)
