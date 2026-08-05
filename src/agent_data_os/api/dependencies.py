"""FastAPI dependencies exposing trusted request state and application services."""

from __future__ import annotations

from fastapi import Request

from agent_data_os.application.query_service import QueryApplicationService
from agent_data_os.application.ingestion_service import IngestionApplicationService
from agent_data_os.core.context import RequestContext
from agent_data_os.domains.policy.ports import PolicyDecisionPort


def get_request_context(request: Request) -> RequestContext:
    return RequestContext(
        request_id=request.state.request_id,
        trace_id=request.state.trace_id,
        security=request.state.security_context,
        environment=request.app.state.container.settings.environment.upper(),
    )


def get_query_service(request: Request) -> QueryApplicationService:
    return request.app.state.container.query_service


def get_policy_service(request: Request) -> PolicyDecisionPort:
    return request.app.state.container.policy_service


def get_ingestion_service(request: Request) -> IngestionApplicationService:
    return request.app.state.container.ingestion_service
