from fastapi import APIRouter
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    logger.debug("Health check requested")
    return {"ok": True}
