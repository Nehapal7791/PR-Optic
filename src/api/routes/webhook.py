from fastapi import APIRouter, Request
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["webhook"])


@router.post("/webhook")
async def handle_webhook(request: Request):
    logger.info("POST /webhook - GitHub webhook received")
    return {"received": True}
