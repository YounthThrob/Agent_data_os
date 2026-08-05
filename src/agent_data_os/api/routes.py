"""V1.0 public and internal HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from agent_data_os.api.dependencies import (
    get_policy_service,
    get_query_service,
    get_request_context,
)
from agent_data_os.api.schemas import PolicyDecisionRequest, QueryRequest
from agent_data_os.application.query_service import QueryApplicationService
from agent_data_os.core.context import ActorType, RequestContext, SecurityContext
from agent_data_os.domains.data_service.models import OrderBy, QueryCommand, QueryFilter
from agent_data_os.domains.policy.models import DecisionRequest, Resource
from agent_data_os.domains.policy.ports import PolicyDecisionPort


router = APIRouter()


@router.get("/health/live", tags=["health"])
def live() -> dict[str, str]:
    """Process liveness; it intentionally has no external dependency checks."""

    return {"status": "UP"}


@router.get("/health/ready", tags=["health"])
def ready(request: Request) -> dict[str, str]:
    """Readiness placeholder; infrastructure probes will be added incrementally."""

    return {
        "status": "READY",
        "service": request.app.state.container.settings.service_name,
        "environment": request.app.state.container.settings.environment,
    }


@router.post(
    "/agent-data/v1/query/{api_code}",
    tags=["agent-data"],
    summary="调用已发布的Query API",
)
def execute_query(
    api_code: str,
    payload: QueryRequest,
    context: RequestContext = Depends(get_request_context),
    service: QueryApplicationService = Depends(get_query_service),
) -> dict[str, object]:
    command = QueryCommand(
        api_code=api_code,
        api_version=payload.api_version,
        selected_fields=tuple(payload.select),
        filters=tuple(
            QueryFilter(item.field, item.op, item.value) for item in payload.filters
        ),
        order_by=tuple(OrderBy(item.field, item.direction) for item in payload.order_by),
        limit=payload.limit,
    )
    result = service.execute(context, command)
    return {
        "request_id": context.request_id,
        "trace_id": context.trace_id,
        "data": {
            "schema": list(result.schema),
            "rows": list(result.rows),
            "next_cursor": None,
        },
        "freshness": {
            "dataset_version": result.dataset_version,
            "as_of": result.freshness_at,
            "status": "FRESH",
        },
        "quality": {"score": result.quality_score, "status": "PASS"},
        "policy": {
            "decision_id": result.decision_id,
            "policy_version": result.policy_version,
            "result_limit_applied": result.result_limit_applied,
        },
        "meta": {
            "api_code": api_code,
            "api_version": payload.api_version,
            "truncated": result.truncated,
        },
    }


@router.post(
    "/internal/v1/policy/decisions",
    tags=["internal"],
    summary="执行单资源策略决策",
)
def decide_policy(
    payload: PolicyDecisionRequest,
    request: Request,
    service: PolicyDecisionPort = Depends(get_policy_service),
) -> dict[str, object]:
    # Internal callers still authenticate at middleware. The tenant supplied in
    # the payload must match the authenticated service context to prevent spoofing.
    caller = request.state.security_context
    if payload.subject.tenant_id != caller.tenant_id:
        from agent_data_os.core.errors import PolicyDeniedError

        raise PolicyDeniedError(["TENANT_CONTEXT_MISMATCH"])

    subject = SecurityContext(
        tenant_id=payload.subject.tenant_id,
        actor_type=ActorType(payload.subject.actor_type),
        actor_id=payload.subject.actor_id,
        purpose=payload.subject.purpose,
        attributes=payload.subject.attributes,
    )
    result = service.decide(
        DecisionRequest(
            subject=subject,
            resource=Resource(
                payload.resource.type,
                payload.resource.id,
                payload.resource.attributes,
            ),
            action=payload.action,
            environment=payload.environment,
        )
    )
    return {
        "request_id": request.state.request_id,
        "trace_id": request.state.trace_id,
        "data": {
            "decision_id": result.decision_id,
            "effect": result.effect.value,
            "policy_version": result.policy_version,
            "obligations": {
                "row_filters": [
                    {"field": f, "op": op, "value": value, "immutable": True}
                    for f, op, value in result.obligations.row_filters
                ],
                "field_masks": [
                    {"field": f, "strategy": strategy}
                    for f, strategy in result.obligations.field_masks
                ],
                "max_rows": result.obligations.max_rows,
                "allow_export": result.obligations.allow_export,
            },
            "reason_codes": list(result.reason_codes),
        },
    }

