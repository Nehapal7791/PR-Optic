"""Tests for webhook receiver and smart routing."""

import pytest
import hmac
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from src.api.routes.webhook import router, WebhookRouter
from src.services.webhook_security import verify_github_signature, WebhookSecurityError
from src.config import Settings
from src.models.state import PRReviewState, OpenIssue
from src.models.review import ReviewScore, Severity


@pytest.fixture
def webhook_secret():
    """Test webhook secret."""
    return "test_secret_key_123"


@pytest.fixture
def sample_pr_opened_payload():
    """Sample GitHub webhook payload for PR opened event."""
    return {
        "action": "opened",
        "pull_request": {
            "number": 1,
            "head": {
                "sha": "abc123def456"
            }
        },
        "repository": {
            "name": "test-repo",
            "owner": {
                "login": "testuser"
            }
        }
    }


@pytest.fixture
def sample_pr_synchronize_payload():
    """Sample GitHub webhook payload for PR synchronize event."""
    return {
        "action": "synchronize",
        "pull_request": {
            "number": 1,
            "head": {
                "sha": "def456abc789"
            }
        },
        "repository": {
            "name": "test-repo",
            "owner": {
                "login": "testuser"
            }
        }
    }


@pytest.fixture
def sample_ping_payload():
    """Sample GitHub webhook payload for ping event."""
    return {
        "zen": "Design for failure.",
        "hook_id": 123456
    }


def compute_signature(payload: bytes, secret: str) -> str:
    """Compute HMAC signature for testing.
    
    Args:
        payload: Request body bytes
        secret: Webhook secret
        
    Returns:
        Signature in format: sha256=<hex>
    """
    signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"


class TestWebhookSecurity:
    """Test webhook security and HMAC verification."""
    
    def test_verify_valid_signature(self, webhook_secret):
        """Test signature verification with valid signature."""
        payload = b'{"test": "data"}'
        signature = compute_signature(payload, webhook_secret)
        
        with patch('src.services.webhook_security.settings') as mock_settings:
            mock_settings.github_webhook_secret = webhook_secret
            assert verify_github_signature(payload, signature) is True
    
    def test_verify_invalid_signature(self, webhook_secret):
        """Test signature verification with invalid signature."""
        payload = b'{"test": "data"}'
        wrong_signature = "sha256=wrong_signature_here"
        
        with patch('src.services.webhook_security.settings') as mock_settings:
            mock_settings.github_webhook_secret = webhook_secret
            
            with pytest.raises(WebhookSecurityError, match="Invalid signature"):
                verify_github_signature(payload, wrong_signature)
    
    def test_verify_missing_signature(self, webhook_secret):
        """Test signature verification with missing signature."""
        payload = b'{"test": "data"}'
        
        with patch('src.services.webhook_security.settings') as mock_settings:
            mock_settings.github_webhook_secret = webhook_secret
            
            with pytest.raises(WebhookSecurityError, match="Missing signature"):
                verify_github_signature(payload, None)
    
    def test_verify_invalid_format(self, webhook_secret):
        """Test signature verification with invalid format."""
        payload = b'{"test": "data"}'
        invalid_signature = "invalid_format_no_equals"
        
        with patch('src.services.webhook_security.settings') as mock_settings:
            mock_settings.github_webhook_secret = webhook_secret
            
            with pytest.raises(WebhookSecurityError, match="Invalid signature format"):
                verify_github_signature(payload, invalid_signature)
    
    def test_verify_unsupported_algorithm(self, webhook_secret):
        """Test signature verification with unsupported algorithm."""
        payload = b'{"test": "data"}'
        signature = "md5=abc123"
        
        with patch('src.services.webhook_security.settings') as mock_settings:
            mock_settings.github_webhook_secret = webhook_secret
            
            with pytest.raises(WebhookSecurityError, match="Unsupported algorithm"):
                verify_github_signature(payload, signature)
    
    def test_verify_no_secret_configured(self):
        """Test signature verification when secret is not configured."""
        payload = b'{"test": "data"}'
        signature = "sha256=abc123"
        
        with patch('src.services.webhook_security.settings') as mock_settings:
            mock_settings.github_webhook_secret = None
            
            with pytest.raises(WebhookSecurityError, match="not configured"):
                verify_github_signature(payload, signature)


class TestWebhookRouter:
    """Test webhook routing logic."""
    
    @pytest.mark.asyncio
    async def test_route_opened_action(self, sample_pr_opened_payload):
        """Test routing for PR opened action."""
        router = WebhookRouter()
        router.orchestrator = AsyncMock()
        
        await router.route_pull_request_event(
            action="opened",
            pull_request=sample_pr_opened_payload["pull_request"],
            repository=sample_pr_opened_payload["repository"]
        )
        
        # Should call orchestrate with correct parameters
        router.orchestrator.orchestrate.assert_called_once_with(
            owner="testuser",
            repo="test-repo",
            pull_number=1,
            commit_sha="abc123def456",
            post_to_github=True
        )
    
    @pytest.mark.asyncio
    async def test_route_synchronize_with_open_issues(self, sample_pr_synchronize_payload):
        """Test routing for synchronize action when PR has open issues."""
        router = WebhookRouter()
        router.orchestrator = AsyncMock()
        
        # Mock state service to return state with open issues
        mock_state = PRReviewState(
            pr_id="testuser/test-repo/1",
            last_reviewed_commit="abc123",
            open_issues=[
                OpenIssue(
                    issue_id="test_issue",
                    filename="test.py",
                    line=10,
                    category="security",
                    severity=Severity.CRITICAL,
                    body="Test issue"
                )
            ],
            last_review_score=ReviewScore.REQUEST_CHANGES,
            last_review_summary="Test summary"
        )
        router.state_service.load = MagicMock(return_value=mock_state)
        
        await router.route_pull_request_event(
            action="synchronize",
            pull_request=sample_pr_synchronize_payload["pull_request"],
            repository=sample_pr_synchronize_payload["repository"]
        )
        
        # Should call orchestrate (which will route to verify_fixes internally)
        router.orchestrator.orchestrate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_route_synchronize_no_state(self, sample_pr_synchronize_payload):
        """Test routing for synchronize action when no state exists."""
        router = WebhookRouter()
        router.orchestrator = AsyncMock()
        router.state_service.load = MagicMock(return_value=None)
        
        await router.route_pull_request_event(
            action="synchronize",
            pull_request=sample_pr_synchronize_payload["pull_request"],
            repository=sample_pr_synchronize_payload["repository"]
        )
        
        # Should call orchestrate (will route to run_review)
        router.orchestrator.orchestrate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_route_other_action_skipped(self, sample_pr_opened_payload):
        """Test that other actions are skipped."""
        router = WebhookRouter()
        router.orchestrator = AsyncMock()
        
        await router.route_pull_request_event(
            action="closed",
            pull_request=sample_pr_opened_payload["pull_request"],
            repository=sample_pr_opened_payload["repository"]
        )
        
        # Should not call orchestrate
        router.orchestrator.orchestrate.assert_not_called()


class TestWebhookEndpoint:
    """Test webhook HTTP endpoint."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)
    
    def test_webhook_with_valid_signature(self, client, webhook_secret, sample_pr_opened_payload):
        """Test webhook endpoint with valid signature."""
        import json
        
        payload_bytes = json.dumps(sample_pr_opened_payload).encode('utf-8')
        signature = compute_signature(payload_bytes, webhook_secret)
        
        with (
            patch('src.api.routes.webhook.verify_github_signature') as mock_verify,
            patch.object(Settings, 'get_allowed_repos', return_value=set()),
        ):
            mock_verify.return_value = True
            
            response = client.post(
                "/webhook",
                content=payload_bytes,
                headers={
                    "X-Hub-Signature-256": signature,
                    "X-GitHub-Event": "pull_request",
                    "Content-Type": "application/json"
                }
            )
        
        assert response.status_code == 200
        assert response.json()["status"] == "received"
        assert response.json()["event"] == "pull_request"
    
    def test_webhook_with_invalid_signature(self, client):
        """Test webhook endpoint with invalid signature."""
        import json
        
        payload = {"test": "data"}
        payload_bytes = json.dumps(payload).encode('utf-8')
        
        with (
            patch('src.api.routes.webhook.verify_github_signature') as mock_verify,
            patch.object(Settings, 'get_allowed_repos', return_value=set()),
        ):
            mock_verify.side_effect = WebhookSecurityError("Invalid signature")
            
            response = client.post(
                "/webhook",
                content=payload_bytes,
                headers={
                    "X-Hub-Signature-256": "sha256=invalid",
                    "X-GitHub-Event": "pull_request"
                }
            )
        
        assert response.status_code == 401
    
    def test_webhook_with_missing_signature(self, client):
        """Test webhook endpoint with missing signature."""
        import json
        
        payload = {"test": "data"}
        payload_bytes = json.dumps(payload).encode('utf-8')
        
        with (
            patch('src.api.routes.webhook.verify_github_signature') as mock_verify,
            patch.object(Settings, 'get_allowed_repos', return_value=set()),
        ):
            mock_verify.side_effect = WebhookSecurityError("Missing signature")
            
            response = client.post(
                "/webhook",
                content=payload_bytes,
                headers={"X-GitHub-Event": "pull_request"}
            )
        
        assert response.status_code == 401
    
    def test_webhook_with_malformed_json(self, client, webhook_secret):
        """Test webhook endpoint with malformed JSON."""
        malformed_payload = b"not valid json {"
        signature = compute_signature(malformed_payload, webhook_secret)
        
        with (
            patch('src.api.routes.webhook.verify_github_signature') as mock_verify,
            patch.object(Settings, 'get_allowed_repos', return_value=set()),
        ):
            mock_verify.return_value = True
            
            response = client.post(
                "/webhook",
                content=malformed_payload,
                headers={
                    "X-Hub-Signature-256": signature,
                    "X-GitHub-Event": "pull_request"
                }
            )
        
        assert response.status_code == 400
    
    def test_webhook_ping_event(self, client, webhook_secret, sample_ping_payload):
        """Test webhook endpoint with ping event."""
        import json
        
        payload_bytes = json.dumps(sample_ping_payload).encode('utf-8')
        signature = compute_signature(payload_bytes, webhook_secret)
        
        with (
            patch('src.api.routes.webhook.verify_github_signature') as mock_verify,
            patch.object(Settings, 'get_allowed_repos', return_value=set()),
        ):
            mock_verify.return_value = True
            
            response = client.post(
                "/webhook",
                content=payload_bytes,
                headers={
                    "X-Hub-Signature-256": signature,
                    "X-GitHub-Event": "ping"
                }
            )
        
        assert response.status_code == 200
        assert response.json()["event"] == "ping"
