"""Structured logging config and the request-id that ties log lines together.

``request_id_var`` is the seam: the middleware sets it per-request,
``OpenAIClient`` reads it when stamping ``llm_calls`` rows so a background
enrichment call (no request) and a chat call (inside a request) both land in
the same table with the right nullable value.
"""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from logging import INFO
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def _request_id(inbound: str | None) -> str:
    if inbound and len(inbound) <= 64 and inbound.isascii():
        return inbound
    return str(uuid4())


def configure_logging() -> None:
    """JSON structlog output with the request id merged into every line."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Honours an inbound ``X-Request-ID``, else mints one; echoes it back."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = _request_id(request.headers.get("X-Request-ID"))
        token = request_id_var.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = request_id
        return response
