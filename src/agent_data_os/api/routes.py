"""V1.0 public and internal HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, Response

from agent_data_os.api.dependencies import (
    get_policy_service,
    get_ingestion_service,
    get_knowledge_service,
    get_query_service,
    get_request_context,
)
from agent_data_os.api.schemas import (
    CompleteIngestionRunRequest,
    CreateDataSourceRequest,
    CreateSyncJobRequest,
    PolicyDecisionRequest,
    QueryRequest,
    CreateFileUploadRequest,
    CreateKnowledgeBaseRequest,
    KnowledgeQueryRequest,
)
from agent_data_os.application.ingestion_service import IngestionApplicationService
from agent_data_os.application.knowledge_service import KnowledgeApplicationService
from agent_data_os.application.query_service import QueryApplicationService
from agent_data_os.core.context import ActorType, RequestContext, SecurityContext
from agent_data_os.domains.data_service.models import OrderBy, QueryCommand, QueryFilter
from agent_data_os.domains.policy.models import DecisionRequest, Resource
from agent_data_os.domains.policy.ports import PolicyDecisionPort


router = APIRouter()


def _require_scope(context: RequestContext, scope: str) -> None:
    if scope not in context.security.scopes:
        from agent_data_os.core.errors import PolicyDeniedError

        raise PolicyDeniedError(["SCOPE_REQUIRED"])


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


@router.post("/api/v1/data-sources", tags=["ingestion"], status_code=201)
def create_data_source(
    payload: CreateDataSourceRequest,
    context: RequestContext = Depends(get_request_context),
    service: IngestionApplicationService = Depends(get_ingestion_service),
) -> dict[str, object]:
    _require_scope(context, "datasource:create")
    source = service.create_data_source(
        context,
        name=payload.name,
        source_type=payload.source_type,
        connector_version=payload.connector_version,
        connection=payload.connection.model_dump(exclude_none=True),
        secret_ref=payload.credential.secret_ref,
        owner_id=payload.owner_id,
    )
    return _source_response(context, source)


@router.post("/api/v1/data-sources/{source_id}/test", tags=["ingestion"])
def test_data_source(
    source_id: str,
    context: RequestContext = Depends(get_request_context),
    service: IngestionApplicationService = Depends(get_ingestion_service),
) -> dict[str, object]:
    _require_scope(context, "datasource:test")
    return _source_response(context, service.test_data_source(context, source_id))


@router.post("/api/v1/data-sources/{source_id}/discover", tags=["ingestion"])
def discover_data_source(
    source_id: str,
    context: RequestContext = Depends(get_request_context),
    service: IngestionApplicationService = Depends(get_ingestion_service),
) -> dict[str, object]:
    _require_scope(context, "datasource:discover")
    return _source_response(context, service.discover_schema(context, source_id))


@router.post("/api/v1/sync-jobs", tags=["ingestion"], status_code=201)
def create_sync_job(
    payload: CreateSyncJobRequest,
    context: RequestContext = Depends(get_request_context),
    service: IngestionApplicationService = Depends(get_ingestion_service),
) -> dict[str, object]:
    _require_scope(context, "sync_job:create")
    job = service.create_sync_job(
        context,
        name=payload.name,
        data_source_id=payload.data_source_id,
        source_objects=tuple(item.model_dump(by_alias=True) for item in payload.source_objects),
        sync_mode=payload.sync_mode,
        target_dataset_name=payload.target.logical_dataset_name,
        schedule=payload.schedule,
        incremental=payload.incremental,
    )
    return {
        "request_id": context.request_id,
        "trace_id": context.trace_id,
        "data": {"id": job.id, "status": job.status.value, "version": job.version},
    }


@router.post("/api/v1/sync-jobs/{job_id}/runs", tags=["ingestion"], status_code=202)
def start_sync_run(
    job_id: str,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    context: RequestContext = Depends(get_request_context),
    service: IngestionApplicationService = Depends(get_ingestion_service),
) -> dict[str, object]:
    _require_scope(context, "sync_job:execute")
    return _run_response(
        context, service.start_run(context, job_id, idempotency_key)
    )


@router.get("/api/v1/sync-runs/{run_id}", tags=["ingestion"])
def get_sync_run(
    run_id: str,
    context: RequestContext = Depends(get_request_context),
    service: IngestionApplicationService = Depends(get_ingestion_service),
) -> dict[str, object]:
    _require_scope(context, "sync_run:read")
    return _run_response(context, service.get_run(context, run_id))


@router.post("/api/v1/sync-runs/{run_id}/retry", tags=["ingestion"], status_code=202)
def retry_sync_run(
    run_id: str,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    context: RequestContext = Depends(get_request_context),
    service: IngestionApplicationService = Depends(get_ingestion_service),
) -> dict[str, object]:
    _require_scope(context, "sync_job:execute")
    return _run_response(
        context, service.retry_run(context, run_id, idempotency_key)
    )


@router.post("/api/v1/sync-runs/{run_id}/cancel", tags=["ingestion"])
def cancel_sync_run(
    run_id: str,
    context: RequestContext = Depends(get_request_context),
    service: IngestionApplicationService = Depends(get_ingestion_service),
) -> dict[str, object]:
    _require_scope(context, "sync_job:execute")
    return _run_response(context, service.cancel_run(context, run_id))


@router.post("/internal/v1/ingestion/runs/{run_id}/callbacks", tags=["internal"])
def complete_sync_run(
    run_id: str,
    payload: CompleteIngestionRunRequest,
    context: RequestContext = Depends(get_request_context),
    service: IngestionApplicationService = Depends(get_ingestion_service),
) -> dict[str, object]:
    _require_scope(context, "ingestion:callback")
    if payload.outcome == "FAILED":
        run = service.fail_run(
            context,
            run_id,
            error_code=payload.error_code or "WORKER_FAILED",
            checkpoint=payload.checkpoint,
        )
        return _run_response(context, run)
    if payload.result_hash is None:
        from agent_data_os.core.errors import InvalidArgumentError

        raise InvalidArgumentError("result_hash is required for a successful callback")
    run = service.complete_run(
        context,
        run_id,
        result_hash=payload.result_hash,
        checkpoint=payload.checkpoint,
        manifest=payload.manifest,
        schema=tuple(payload.schema_definition),
        rows=tuple(payload.rows),
    )
    return _run_response(context, run)


def _source_response(context: RequestContext, source: object) -> dict[str, object]:
    # Secret references and credentials are intentionally absent from responses.
    return {
        "request_id": context.request_id,
        "trace_id": context.trace_id,
        "data": {
            "id": source.id,
            "name": source.name,
            "source_type": source.source_type,
            "status": source.status.value,
            "credential_status": "CONFIGURED",
            "schema_objects": list(source.discovered_schema),
            "version": source.version,
        },
    }


def _run_response(context: RequestContext, run: object) -> dict[str, object]:
    return {
        "request_id": context.request_id,
        "trace_id": context.trace_id,
        "data": {
            "id": run.id,
            "sync_job_id": run.sync_job_id,
            "status": run.status.value,
            "checkpoint": run.checkpoint,
            "row_count": run.row_count,
            "dataset_version_id": run.dataset_version_id,
            "error_code": run.error_code,
        },
    }


@router.post("/api/v1/knowledge-bases", tags=["knowledge"], status_code=201)
def create_knowledge_base(
    payload: CreateKnowledgeBaseRequest,
    context: RequestContext = Depends(get_request_context),
    service: KnowledgeApplicationService = Depends(get_knowledge_service),
) -> dict[str, object]:
    _require_scope(context, "knowledge_base:create")
    value = service.create_knowledge_base(
        context,
        code=payload.code,
        name=payload.name,
        owner_id=payload.owner_id,
        allowed_purposes=frozenset(payload.allowed_purposes),
        max_top_k=payload.max_top_k,
        allow_generation=payload.allow_generation,
    )
    return {
        "request_id": context.request_id,
        "trace_id": context.trace_id,
        "data": {"id": value.id, "code": value.code, "status": value.status.value},
    }


@router.post("/api/v1/files/uploads", tags=["knowledge"], status_code=201)
def create_file_upload(
    payload: CreateFileUploadRequest,
    context: RequestContext = Depends(get_request_context),
    service: KnowledgeApplicationService = Depends(get_knowledge_service),
) -> dict[str, object]:
    _require_scope(context, "file:upload")
    document, version, upload_url = service.create_upload(
        context,
        knowledge_base_id=payload.knowledge_base_id,
        file_name=payload.file_name,
        size_bytes=payload.size_bytes,
        mime_type=payload.mime_type,
        sha256=payload.sha256,
        classification=payload.classification,
        acl_tokens=frozenset(payload.acl_tokens),
    )
    return {
        "request_id": context.request_id,
        "trace_id": context.trace_id,
        "data": {
            "document_id": document.id,
            "document_version_id": version.id,
            "upload_url": upload_url,
            "expires_in_seconds": 900,
        },
    }


@router.post(
    "/internal/v1/knowledge/document-versions/{version_id}/process",
    tags=["internal"],
)
def process_document_version(
    version_id: str,
    context: RequestContext = Depends(get_request_context),
    service: KnowledgeApplicationService = Depends(get_knowledge_service),
) -> dict[str, object]:
    _require_scope(context, "knowledge:process")
    index = service.process_document(context, version_id)
    return {
        "request_id": context.request_id,
        "trace_id": context.trace_id,
        "data": {
            "index_version_id": index.id,
            "version_number": index.version_number,
            "status": index.status.value,
            "chunk_count": index.chunk_count,
        },
    }


@router.post(
    "/api/v1/knowledge-bases/{kb_id}/indexes/{index_id}/publish",
    tags=["knowledge"],
)
def publish_knowledge_index(
    kb_id: str,
    index_id: str,
    context: RequestContext = Depends(get_request_context),
    service: KnowledgeApplicationService = Depends(get_knowledge_service),
) -> dict[str, object]:
    _require_scope(context, "knowledge_index:publish")
    kb = service.publish_index(context, kb_id, index_id)
    return {
        "request_id": context.request_id,
        "trace_id": context.trace_id,
        "data": {
            "knowledge_base_id": kb.id,
            "active_index_version_id": kb.active_index_version_id,
            "version": kb.version,
        },
    }


@router.post("/agent-data/v1/knowledge/{api_code}", tags=["agent-data"])
def retrieve_knowledge(
    api_code: str,
    payload: KnowledgeQueryRequest,
    response: Response,
    context: RequestContext = Depends(get_request_context),
    service: KnowledgeApplicationService = Depends(get_knowledge_service),
) -> dict[str, object]:
    _require_scope(context, "knowledge_api:invoke")
    result = service.retrieve(
        context,
        api_code=api_code,
        query=payload.query,
        top_k=payload.top_k,
        generate_answer=payload.generate_answer,
        fail_on_insufficient_evidence=payload.fail_on_insufficient_evidence,
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "request_id": context.request_id,
        "trace_id": context.trace_id,
        "data": {
            "answer": result.answer,
            "sufficient_evidence": result.sufficient_evidence,
            "evidence": [
                {
                    "chunk_id": item.chunk_id,
                    "document_id": item.document_id,
                    "document_version_id": item.document_version_id,
                    "title": item.title,
                    "excerpt": item.excerpt,
                    "score": item.score,
                    "citation": {
                        "page": item.page_number,
                        "classification": item.classification,
                    },
                }
                for item in result.evidence
            ],
        },
        "retrieval": {
            "knowledge_base_id": result.knowledge_base_id,
            "index_version_id": result.index_version_id,
            "candidate_count": result.candidate_count,
            "authorized_count": result.authorized_count,
            "returned_count": len(result.evidence),
        },
        "model": {"generated": result.generated},
        "warnings": (
            []
            if result.sufficient_evidence
            else [{"code": "INSUFFICIENT_EVIDENCE"}]
        ),
    }
