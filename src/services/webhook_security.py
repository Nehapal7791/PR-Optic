"""
Webhook Security - HMAC Signature Verification

Verifies GitHub webhook signatures to ensure requests are genuine.
"""

import hmac
import hashlib
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class WebhookSecurityError(Exception):
    """Raised when webhook security validation fails."""
    pass


def verify_github_signature(payload_body: bytes, signature_header: str | None) -> bool:
    """Verify GitHub webhook HMAC signature.
    
    GitHub sends X-Hub-Signature-256 header with format: sha256=<signature>
    We compute HMAC-SHA256 of payload with our secret and compare.
    
    Args:
        payload_body: Raw request body bytes
        signature_header: Value of X-Hub-Signature-256 header
        
    Returns:
        True if signature is valid
        
    Raises:
        WebhookSecurityError: If signature is missing or invalid
    """
    if not signature_header:
        logger.error("Missing X-Hub-Signature-256 header")
        raise WebhookSecurityError("Missing signature header")
    
    if not settings.github_webhook_secret:
        logger.error("GITHUB_WEBHOOK_SECRET not configured")
        raise WebhookSecurityError("Webhook secret not configured")
    
    # Extract signature from header (format: sha256=<hex_signature>)
    try:
        algorithm, signature = signature_header.split("=", 1)
    except ValueError:
        logger.error(f"Invalid signature header format: {signature_header}")
        raise WebhookSecurityError("Invalid signature format")
    
    if algorithm != "sha256":
        logger.error(f"Unsupported signature algorithm: {algorithm}")
        raise WebhookSecurityError(f"Unsupported algorithm: {algorithm}")
    
    # Compute expected signature
    secret_bytes = settings.github_webhook_secret.encode('utf-8')
    expected_signature = hmac.new(
        secret_bytes,
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    # Constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(expected_signature, signature)
    
    if not is_valid:
        logger.error("Signature verification failed - possible tampering or wrong secret")
        raise WebhookSecurityError("Invalid signature")
    
    logger.debug("Signature verified successfully")
    return True
