"""Tests for webhook routing logic."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.api.routes.webhook import WebhookRouter


class TestWebhookRouting:
    """Test webhook routing decisions."""
    
    @pytest.fixture
    def router(self):
        """Create webhook router instance."""
        return WebhookRouter()
    
    @pytest.fixture
    def mock_orchestrator(self, router):
        """Mock the review orchestrator."""
        router.orchestrator.orchestrate = AsyncMock()
        return router.orchestrator
    
    @pytest.fixture
    def mock_state_service(self, router):
        """Mock the state service."""
        router.state_service.load = MagicMock()
        return router.state_service
    
    @pytest.mark.asyncio
    async def test_opened_action_triggers_review(self, router, mock_orchestrator):
        """Test that 'opened' action triggers new review."""
        pull_request = {
            "number": 123,
            "head": {"sha": "abc123def456"}
        }
        repository = {
            "owner": {"login": "ddevilz"},
            "name": "Terraform"
        }
        
        await router.route_pull_request_event(
            action="opened",
            pull_request=pull_request,
            repository=repository
        )
        
        # Should call orchestrate with correct params
        mock_orchestrator.orchestrate.assert_called_once_with(
            owner="ddevilz",
            repo="Terraform",
            pull_number=123,
            commit_sha="abc123def456",
            post_to_github=True
        )
    
    @pytest.mark.asyncio
    async def test_synchronize_with_open_issues_triggers_verification(
        self, router, mock_orchestrator, mock_state_service
    ):
        """Test that 'synchronize' with open issues triggers fix verification."""
        # Mock state with open issues
        mock_state = MagicMock()
        mock_state.open_issues = [{"id": "issue1"}]
        mock_state_service.load.return_value = mock_state
        
        pull_request = {
            "number": 123,
            "head": {"sha": "def456ghi789"}
        }
        repository = {
            "owner": {"login": "ddevilz"},
            "name": "Terraform"
        }
        
        await router.route_pull_request_event(
            action="synchronize",
            pull_request=pull_request,
            repository=repository
        )
        
        # Should load state
        mock_state_service.load.assert_called_once_with("ddevilz/Terraform/123")
        
        # Should call orchestrate (which will route to verification)
        mock_orchestrator.orchestrate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_synchronize_without_state_triggers_new_review(
        self, router, mock_orchestrator, mock_state_service
    ):
        """Test that 'synchronize' without state triggers new review."""
        # Mock no existing state
        mock_state_service.load.return_value = None
        
        pull_request = {
            "number": 123,
            "head": {"sha": "ghi789jkl012"}
        }
        repository = {
            "owner": {"login": "ddevilz"},
            "name": "Terraform"
        }
        
        await router.route_pull_request_event(
            action="synchronize",
            pull_request=pull_request,
            repository=repository
        )
        
        # Should call orchestrate for new review
        mock_orchestrator.orchestrate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_other_actions_skipped(self, router, mock_orchestrator):
        """Test that other actions are skipped."""
        pull_request = {
            "number": 123,
            "head": {"sha": "xyz789"}
        }
        repository = {
            "owner": {"login": "ddevilz"},
            "name": "Terraform"
        }
        
        # Test various actions that should be skipped
        for action in ["closed", "edited", "labeled", "assigned"]:
            await router.route_pull_request_event(
                action=action,
                pull_request=pull_request,
                repository=repository
            )
        
        # Should never call orchestrate
        mock_orchestrator.orchestrate.assert_not_called()
