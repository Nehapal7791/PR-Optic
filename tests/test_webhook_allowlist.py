"""Tests for webhook repository allowlist validation."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import hmac
import hashlib
import json
from src.main import app
from src.config import settings
from src.api.routes import webhook as webhook_module


class TestWebhookAllowlist:
    """Test repository allowlist functionality."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def _clear_delivery_cache(self):
        webhook_module._processed_deliveries.clear()
    
    def _generate_signature(self, payload: bytes) -> str:
        """Generate valid GitHub webhook signature."""
        secret = settings.github_webhook_secret.encode('utf-8')
        signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        return f"sha256={signature}"
    
    def _create_webhook_payload(self, repo_full_name: str) -> dict:
        """Create a minimal webhook payload."""
        return {
            "action": "opened",
            "pull_request": {
                "number": 123,
                "head": {"sha": "abc123"}
            },
            "repository": {
                "full_name": repo_full_name,
                "owner": {"login": repo_full_name.split("/")[0]},
                "name": repo_full_name.split("/")[1]
            }
        }
    
    @patch('src.config.Settings.get_allowed_repos')
    def test_allowed_repo_accepted(self, mock_get_allowed, client):
        """Test that allowed repository is accepted."""
        # Configure allowlist
        mock_get_allowed.return_value = {"ddevilz/Terraform", "user/repo2"}
        
        payload = self._create_webhook_payload("ddevilz/Terraform")
        payload_bytes = json.dumps(payload).encode('utf-8')
        signature = self._generate_signature(payload_bytes)
        
        response = client.post(
            "/api/webhook",
            content=payload_bytes,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "test-delivery-1",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "received"
    
    @patch('src.config.Settings.get_allowed_repos')
    def test_disallowed_repo_rejected(self, mock_get_allowed, client):
        """Test that disallowed repository is rejected."""
        # Configure allowlist (doesn't include unauthorized/repo)
        mock_get_allowed.return_value = {"ddevilz/Terraform", "user/repo2"}
        
        payload = self._create_webhook_payload("unauthorized/repo")
        payload_bytes = json.dumps(payload).encode('utf-8')
        signature = self._generate_signature(payload_bytes)
        
        response = client.post(
            "/api/webhook",
            content=payload_bytes,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "test-delivery-2",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"]
    
    @patch('src.config.Settings.get_allowed_repos')
    def test_empty_allowlist_accepts_all(self, mock_get_allowed, client):
        """Test that empty allowlist accepts all repositories."""
        # Empty allowlist = allow all
        mock_get_allowed.return_value = set()
        
        payload = self._create_webhook_payload("any/repository")
        payload_bytes = json.dumps(payload).encode('utf-8')
        signature = self._generate_signature(payload_bytes)
        
        response = client.post(
            "/api/webhook",
            content=payload_bytes,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "test-delivery-3",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "received"
    
    def test_duplicate_delivery_skipped(self, client):
        """Test that duplicate delivery IDs are skipped."""
        payload = self._create_webhook_payload("ddevilz/Terraform")
        payload_bytes = json.dumps(payload).encode('utf-8')
        signature = self._generate_signature(payload_bytes)
        
        headers = {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "duplicate-test-delivery",
            "Content-Type": "application/json"
        }
        
        # First request
        response1 = client.post("/api/webhook", content=payload_bytes, headers=headers)
        assert response1.status_code == 200
        
        # Second request with same delivery ID
        response2 = client.post("/api/webhook", content=payload_bytes, headers=headers)
        assert response2.status_code == 200
        assert response2.json()["status"] == "skipped"
        assert response2.json()["reason"] == "duplicate_delivery"
