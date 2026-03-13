from fastapi import APIRouter
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["github"])


@router.get("/repos")
async def list_repos():
    logger.info("GET /api/repos - Listing repositories")
    return {"repos": []}


@router.get("/pulls")
async def list_pulls():
    logger.info("GET /api/pulls - Listing pull requests")
    return {"pulls": []}
