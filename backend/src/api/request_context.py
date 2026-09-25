"""
request_context.py — per-request correlation IDs
================================================
Every request is tagged with a short id that is:

    * returned in the ``X-Request-ID`` response header,
    * included in every error payload produced by the exception handlers in
      :mod:`src.api.errors`, and
    * written to the server log alongside the error.

The point is supportability: a user who sees a failure can quote the reference
in the message, and that reference appears verbatim in the container log, so a
report can be traced to one log line without reproducing it.
"""

from __future__ import annotations

import contextvars
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_LENGTH = 12

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def new_request_id() -> str:
    """Return a short correlation id safe to show a user in an error message."""
    return uuid.uuid4().hex[:_REQUEST_ID_LENGTH]


def resolve_request_id(request: Request | None = None) -> str | None:
    """Return the correlation id for ``request``.

    ``request.state`` is preferred because it survives the middleware
    unwinding, which is what happens for unhandled exceptions - those are
    rendered by the outermost error handler, after this middleware has already
    returned. The context variable is the fallback for code that only has the
    ambient request.
    """
    if request is not None:
        value = getattr(request.state, "request_id", None)
        if value:
            return value
    return _request_id_var.get()


def current_request_id() -> str | None:
    """Return the correlation id of the request being handled, if any."""
    return _request_id_var.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Tag each request with a correlation id and echo it back as a header."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        request.state.request_id = request_id
        token = _request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
