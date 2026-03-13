import pytest
from src.services.claude_service import ClaudeService


@pytest.mark.asyncio
async def test_claude_service_init():
    service = ClaudeService()
    assert service.client is not None
