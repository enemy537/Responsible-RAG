"""Domain errors that map onto HTTP responses."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.request_context import REQUEST_ID_HEADER, resolve_request_id

logger = logging.getLogger(__name__)


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


def _error_response(request: Request, status_code: int, detail: str) -> JSONResponse:
    """Build a JSON error response carrying the request's correlation id.

    ``request_id`` is included in the body (not just the header) so clients can
    surface it to the user without needing access to response headers - which
    cross-origin requests cannot read unless the header is explicitly exposed.
    """
    request_id = resolve_request_id(request)
    content: dict[str, str] = {"detail": detail}
    headers: dict[str, str] | None = None
    if request_id:
        content["request_id"] = request_id
        headers = {REQUEST_ID_HEADER: request_id}
    return JSONResponse(status_code=status_code, content=content, headers=headers)


def _log_failure(request: Request, status_code: int, detail: str) -> None:
    """Log a handled failure with enough context to trace a user report."""
    logger.log(
        logging.ERROR if status_code >= 500 else logging.WARNING,
        "%s %s -> %d [%s] %s",
        request.method,
        request.url.path,
        status_code,
        resolve_request_id(request),
        detail,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Translate errors into JSON responses that carry a correlation id.

    Three handlers are registered so that *every* failure path returns the same
    shape and is logged with the same reference:

    * :class:`AppError` - expected domain failures.
    * :class:`StarletteHTTPException` - ``HTTPException`` raised in routes.
    * :class:`Exception` - everything else. Without this, an unhandled error
      returns a bare 500 and the user sees nothing actionable.
    """

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        _log_failure(request, exc.status_code, exc.detail)
        return _error_response(request, exc.status_code, exc.detail)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        _log_failure(request, exc.status_code, detail)
        response = _error_response(request, exc.status_code, detail)
        for key, value in (exc.headers or {}).items():
            response.headers.setdefault(key, value)
        return response

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled error on %s %s [%s]",
            request.method,
            request.url.path,
            resolve_request_id(request),
        )
        return _error_response(request, 500, "Internal server error")
