from fastapi import FastAPI
from src.api.routes import github, reviews, webhook, health
from src.middleware.error_handler import add_error_handlers
from src.utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(title="PR-Optic", version="0.1.0")

logger.info("Initializing PR-Optic FastAPI application")

add_error_handlers(app)

app.include_router(health.router)
app.include_router(github.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(webhook.router, prefix="/api")

logger.info("All routes registered successfully")


@app.on_event("startup")
async def startup_event():
    logger.info(" PR-Optic application started")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 PR-Optic application shutting down")
