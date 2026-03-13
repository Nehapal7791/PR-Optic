import pytest
from src.services.github_service import GitHubService


@pytest.mark.asyncio
async def test_github_service_init():
    service = GitHubService()
    assert service.base_url == "https://api.github.com"
