"""
AI Service Factory

Creates the appropriate AI provider based on configuration.
Supports: Gemini (default/free), Claude, GitHub Models
"""

from src.config import settings
from src.utils.logger import get_logger
from src.services.ai_provider import AIProvider
from src.services.providers.gemini_provider import GeminiProvider
from src.services.providers.claude_provider import ClaudeProvider
from src.services.providers.github_models_provider import GitHubModelsProvider

logger = get_logger(__name__)


def get_ai_provider() -> AIProvider:
    """Get the configured AI provider.
    
    Returns:
        AIProvider instance based on AI_PROVIDER config
    
    Raises:
        ValueError: If provider is unknown or required API key is missing
    """
    provider_name = settings.ai_provider.lower()
    
    logger.info(f"Initializing AI provider: {provider_name}")
    
    if provider_name == "gemini":
        if not settings.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is required when AI_PROVIDER=gemini. "
                "Get a free key at: https://aistudio.google.com/apikey"
            )
        return GeminiProvider()
    
    elif provider_name == "claude":
        if not settings.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required when AI_PROVIDER=claude. "
                "Note: Claude requires credits. Consider using Gemini (free)."
            )
        return ClaudeProvider()
    
    elif provider_name == "github_models":
        if not settings.github_model_token:
            raise ValueError(
                "GITHUB_MODEL_TOKEN is required when AI_PROVIDER=github_models. "
                "Generate token at: https://github.com/marketplace/models"
            )
        return GitHubModelsProvider()
    
    else:
        raise ValueError(
            f"Unknown AI provider: {provider_name}. "
            f"Supported providers: gemini, claude, github_models"
        )


# Singleton instance
_ai_provider: AIProvider | None = None


def get_ai_service() -> AIProvider:
    """Get singleton AI provider instance.
    
    Returns:
        Cached AIProvider instance
    """
    global _ai_provider
    
    if _ai_provider is None:
        _ai_provider = get_ai_provider()
        logger.info(f"AI service initialized: {_ai_provider.provider_name}")
    
    return _ai_provider
