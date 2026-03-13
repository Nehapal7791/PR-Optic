import hmac
import hashlib
from fastapi import Request, HTTPException
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def verify_webhook_signature(request: Request):
    signature = request.headers.get("X-Hub-Signature-256")
    
    if not signature:
        logger.warning("Webhook request missing X-Hub-Signature-256 header")
        raise HTTPException(status_code=401, detail="Missing signature")
    
    body = await request.body()
    expected = "sha256=" + hmac.new(
        settings.github_webhook_secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected):
        logger.error("Webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    logger.info("Webhook signature verified successfully")
