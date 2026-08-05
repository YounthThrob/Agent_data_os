"""FastAPI application factory for Agent Data OS V1.0."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agent_data_os.api.routes import router
from agent_data_os.container import build_container
from agent_data_os.core.config import Settings, get_settings
from agent_data_os.core.errors import AppError
from agent_data_os.core.identity import build_identity_resolver
from agent_data_os.core.middleware import RequestContextMiddleware
from agent_data_os.infrastructure.connectors import SecretResolver


def create_app(
    settings: Settings | None = None,
    secret_resolver: SecretResolver | None = None,
) -> FastAPI:
    """Create the application with explicit dependency composition."""

    settings = settings or get_settings()
    settings.validate()
    container = build_container(settings, secret_resolver)
    identity_resolver = build_identity_resolver(settings)

    app = FastAPI(
        title="Agent Data OS API",
        version="0.1.0",
        description="Agent Data OS V1.0 implementation baseline",
    )
    app.state.container = container
    app.add_middleware(
        RequestContextMiddleware,
        settings=settings,
        identity_resolver=identity_resolver,
    )

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "request_id": getattr(request.state, "request_id", None),
                "trace_id": getattr(request.state, "trace_id", None),
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "retryable": exc.retryable,
                    "documentation_url": f"/docs/errors/{exc.code}",
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in error["loc"]),
                "reason": error["type"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=400,
            content={
                "request_id": getattr(request.state, "request_id", None),
                "trace_id": getattr(request.state, "trace_id", None),
                "error": {
                    "code": "INVALID_ARGUMENT",
                    "message": "请求参数不合法",
                    "details": details,
                    "retryable": False,
                },
            },
        )

    app.include_router(router)
    return app


app = create_app()
