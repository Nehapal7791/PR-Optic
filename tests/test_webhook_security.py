"""Tests for webhook security and signature verification."""

import pytest
import hmac
import hashlib
from src.services.webhook_security import verify_github_signature, WebhookSecurityError
from src.config import settings


class TestWebhookSecurity:
    """Test webhook signature verification."""
    
    def test_valid_signature(self):
        """Test that valid signature passes verification."""
        payload = b'{"action": "opened", "number": 1}'
        secret = settings.github_webhook_secret.encode('utf-8')
        
        # Generate valid signature
        signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        signature_header = f"sha256={signature}"
        
        # Should not raise
        assert verify_github_signature(payload, signature_header) is True
    
    def test_invalid_signature(self):
        """Test that invalid signature raises error."""
        payload = b'{"action": "opened", "number": 1}'
        signature_header = "sha256=invalid_signature_here"
        
        with pytest.raises(WebhookSecurityError, match="Invalid signature"):
            verify_github_signature(payload, signature_header)
    
    def test_missing_signature_header(self):
        """Test that missing signature header raises error."""
        payload = b'{"action": "opened", "number": 1}'
        
        with pytest.raises(WebhookSecurityError, match="Missing signature header"):
            verify_github_signature(payload, None)
    
    def test_wrong_algorithm(self):
        """Test that wrong algorithm raises error."""
        payload = b'{"action": "opened", "number": 1}'
        signature_header = "sha1=somehash"
        
        with pytest.raises(WebhookSecurityError, match="Unsupported algorithm"):
            verify_github_signature(payload, signature_header)
    
    def test_malformed_signature_header(self):
        """Test that malformed signature header raises error."""
        payload = b'{"action": "opened", "number": 1}'
        signature_header = "malformed_header_without_equals"
        
        with pytest.raises(WebhookSecurityError, match="Invalid signature format"):
            verify_github_signature(payload, signature_header)
    
    def test_tampered_payload(self):
        """Test that tampered payload fails verification."""
        original_payload = b'{"action": "opened", "number": 1}'
        tampered_payload = b'{"action": "opened", "number": 999}'
        
        secret = settings.github_webhook_secret.encode('utf-8')
        signature = hmac.new(secret, original_payload, hashlib.sha256).hexdigest()
        signature_header = f"sha256={signature}"
        
        with pytest.raises(WebhookSecurityError, match="Invalid signature"):
            verify_github_signature(tampered_payload, signature_header)
