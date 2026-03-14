"""
Base AI Provider Interface

Defines the contract that all AI providers (Gemini, Claude, GitHub Models) must implement.
"""

from abc import ABC, abstractmethod
from src.models.github import PRFile
from src.models.review import TriageResult, ReviewResult, ConcernCategory


class AIProvider(ABC):
    """Abstract base class for AI providers."""
    
    @abstractmethod
    async def triage_diff(
        self,
        files: list[PRFile],
        pr_title: str,
        pr_body: str | None
    ) -> TriageResult:
        """First pass: Classify diff into concern categories.
        
        Args:
            files: List of changed files with patches
            pr_title: Pull request title
            pr_body: Pull request description
        
        Returns:
            TriageResult with identified concern categories
        """
        pass
    
    @abstractmethod
    async def review_pull_request(
        self,
        files: list[PRFile],
        pr_title: str,
        pr_body: str | None,
        categories: list[ConcernCategory]
    ) -> ReviewResult:
        """Second pass: Focused review per identified category.
        
        Args:
            files: List of changed files with patches
            pr_title: Pull request title
            pr_body: Pull request description
            categories: Concern categories from triage
        
        Returns:
            ReviewResult with grouped comments and score
        """
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this provider."""
        pass
    
    @property
    @abstractmethod
    def max_tokens(self) -> int:
        """Return the max tokens for this provider."""
        pass
