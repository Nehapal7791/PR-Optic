from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GitHubAPIError(Exception):
    """Exception raised when GitHub API calls fail."""
    pass


class AIServiceError(Exception):
    """Exception raised when AI service calls fail."""
    pass


def add_error_handlers(app: FastAPI):
    @app.exception_handler(GitHubAPIError)
    async def github_api_error_handler(request: Request, exc: GitHubAPIError):
        logger.error(
            f"GitHub API error: {exc}",
            exc_info=True,
            extra={"path": request.url.path, "method": request.method}
        )
        return JSONResponse(
            status_code=502,
            content={
                "error": str(exc),
                "type": "GitHubAPIError",
                "hint": "GitHub API is unavailable. Please try again later."
            }
        )
    
    @app.exception_handler(AIServiceError)
    async def ai_service_error_handler(request: Request, exc: AIServiceError):
        logger.error(
            f"AI service error: {exc}",
            exc_info=True,
            extra={"path": request.url.path, "method": request.method}
        )
        return JSONResponse(
            status_code=503,
            content={
                "error": str(exc),
                "type": "AIServiceError",
                "hint": "AI service is temporarily unavailable. Please try again."
            }
        )
    
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
