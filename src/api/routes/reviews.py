from fastapi import APIRouter
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["reviews"])


@router.post("/reviews")
async def trigger_review():
    logger.info("POST /api/reviews - Manual review triggered")
    return {"status": "triggered"}
