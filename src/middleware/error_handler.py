from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from src.utils.logger import get_logger

logger = get_logger(__name__)


def add_error_handlers(app: FastAPI):
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(
            f"Unhandled exception: {type(exc).__name__}: {exc}",
            exc_info=True,
            extra={"path": request.url.path, "method": request.method}
        )
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "type": type(exc).__name__}
        )
