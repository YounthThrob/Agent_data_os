"""HTTP middleware for correlation identifiers and trusted request context."""

from __future__ import annotations

import re
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from agent_data_os.core.config import Settings
from agent_data_os.core.errors import AppError
from agent_data_os.core.identity import IdentityResolver


_TRACEPARENT_PATTERN = re.compile(
    r"^[\da-f]{2}-([\da-f]{32})-([\da-f]{16})-[\da-f]{2}$", re.IGNORECASE
)


def _new_identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _trace_id_from_header(traceparent: str | None) -> str:
    if traceparent:
        match = _TRACEPARENT_PATTERN.match(traceparent)
        if match:
            return match.group(1).lower()
    return uuid.uuid4().hex


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request/trace IDs and resolve identity for protected API paths."""

    def __init__(
        self,
        app: object,
        *,
        settings: Settings,
        identity_resolver: IdentityResolver,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._settings = settings
        self._identity_resolver = identity_resolver

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-Id") or _new_identifier("req")
        trace_id = _trace_id_from_header(request.headers.get("traceparent"))
        request.state.request_id = request_id
        request.state.trace_id = trace_id

        # Health and OpenAPI endpoints remain unauthenticated. Protected routes
        # resolve identity here so downstream code never trusts raw tenant headers.
        protected = request.url.path.startswith(("/api/", "/agent-data/", "/internal/"))
        if protected:
            try:
                request.state.security_context = self._identity_resolver.resolve(
                    request.headers.get("Authorization"),
                    request.headers.get("X-Purpose"),
                )
            except AppError as exc:
                # Exceptions raised before ``call_next`` do not pass through
                # FastAPI's route exception handlers, so the middleware must
                # preserve the same stable error envelope itself.
                response = JSONResponse(
                    status_code=exc.status_code,
                    content={
                        "request_id": request_id,
                        "trace_id": trace_id,
                        "error": {
                            "code": exc.code,
                            "message": exc.message,
                            "details": exc.details,
                            "retryable": exc.retryable,
                            "documentation_url": f"/docs/errors/{exc.code}",
                        },
                    },
                )
                response.headers["X-Request-Id"] = request_id
                response.headers["X-Trace-Id"] = trace_id
                response.headers["X-Content-Type-Options"] = "nosniff"
                return response

        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
