"""Domain errors that map onto HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application error carrying an HTTP status code."""

    status_code: int = 500
    detail: str = "Internal server error"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.detail
        super().__init__(self.detail)


class ValidationError(AppError):
    status_code = 400
    detail = "Invalid request"


class NotFoundError(AppError):
    status_code = 404
    detail = "Resource not found"


class ForbiddenError(AppError):
    status_code = 403
    detail = "Forbidden"


class UnauthorizedError(AppError):
    status_code = 401
    detail = "Not authenticated"


class ConflictError(AppError):
    status_code = 409
    detail = "Resource already exists"


class DatabaseUnavailableError(AppError):
    status_code = 503
    detail = "Database not available"


def register_exception_handlers(app: FastAPI) -> None:
    """Translate :class:`AppError` subclasses into JSON error responses."""

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
