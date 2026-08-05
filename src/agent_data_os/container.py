"""Composition root assembling domain services and infrastructure adapters."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine

from agent_data_os.application.query_service import QueryApplicationService
from agent_data_os.core.config import Settings
from agent_data_os.domains.data_service.models import QueryApiDefinition
from agent_data_os.domains.policy.models import Grant
from agent_data_os.domains.policy.service import PolicyEvaluator
from agent_data_os.infrastructure.memory import (
    InMemoryAuditRecorder,
    InMemoryPolicyRepository,
    InMemoryQueryApiRepository,
    InMemoryQueryDataPort,
)
from agent_data_os.infrastructure.persistence.database import (
    build_engine,
    build_session_factory,
    initialize_schema,
)
from agent_data_os.infrastructure.persistence.repositories import (
    SqlAlchemyAuditRecorder,
    SqlAlchemyPolicyRepository,
    SqlAlchemyQueryApiRepository,
)


@dataclass(slots=True)
class Container:
    settings: Settings
    policy_service: PolicyEvaluator
    query_service: QueryApplicationService
    audit_recorder: object
    engine: Engine | None = None


def build_container(settings: Settings) -> Container:
    """Build V1.0 dependencies.

    Development fixtures are isolated here so replacing them with PostgreSQL and
    a remote PDP does not change API or domain code.
    """

    definitions: dict[tuple[str, str], QueryApiDefinition] = {}
    datasets: dict[tuple[str, str], list[dict[str, object]]] = {}
    grants: list[Grant] = []

    if settings.environment in {"development", "test"}:
        definition = QueryApiDefinition(
            code="customer_receivable_query",
            version="1.0.0",
            dataset_id="dataset_receivable",
            selectable_fields=frozenset(
                {
                    "customer_name",
                    "region",
                    "overdue_amount",
                    "currency",
                    "overdue_days",
                }
            ),
            allowed_filters={
                "region": frozenset({"eq", "in"}),
                "overdue_days": frozenset({"eq", "gte", "lte"}),
                "overdue_amount": frozenset({"gte", "lte"}),
            },
            allowed_order_fields=frozenset({"overdue_amount", "overdue_days"}),
            allowed_purposes=frozenset({"sales_risk_followup"}),
            default_limit=settings.default_query_limit,
            maximum_limit=settings.max_query_limit,
            dataset_version=12,
            freshness_at="2026-08-04T01:00:00Z",
            quality_score=96.0,
            field_types={
                "customer_name": "string",
                "region": "string",
                "overdue_amount": "decimal",
                "currency": "string",
                "overdue_days": "integer",
            },
        )
        definitions[("tenant_001", definition.code)] = definition
        datasets[("tenant_001", definition.dataset_id)] = [
            {
                "customer_name": "华东示例客户A",
                "region": "EAST",
                "overdue_amount": "320000.00",
                "currency": "CNY",
                "overdue_days": 45,
            },
            {
                "customer_name": "华南示例客户B",
                "region": "SOUTH",
                "overdue_amount": "510000.00",
                "currency": "CNY",
                "overdue_days": 62,
            },
            {
                "customer_name": "华东示例客户C",
                "region": "EAST",
                "overdue_amount": "88000.00",
                "currency": "CNY",
                "overdue_days": 12,
            },
        ]
        grants.append(
            Grant(
                tenant_id="tenant_001",
                actor_id="sales_risk_agent",
                resource_type="DATA_API_VERSION",
                resource_id="customer_receivable_query:1.0.0",
                action="INVOKE",
                purposes=frozenset({"sales_risk_followup"}),
                region_from_subject=True,
                max_rows=20,
            )
        )

    engine: Engine | None = None
    if settings.database_url:
        engine = build_engine(settings)
        initialize_schema(engine, settings)
        sessions = build_session_factory(engine)
        policy_repository = SqlAlchemyPolicyRepository(sessions)
        api_repository = SqlAlchemyQueryApiRepository(sessions)
        audit_recorder = SqlAlchemyAuditRecorder(sessions)
    else:
        policy_repository = InMemoryPolicyRepository(grants)
        api_repository = InMemoryQueryApiRepository(definitions)
        audit_recorder = InMemoryAuditRecorder()

    policy_service = PolicyEvaluator(policy_repository, policy_version=1)
    query_service = QueryApplicationService(
        api_repository,
        InMemoryQueryDataPort(datasets),
        policy_service,
        audit_recorder,
    )
    return Container(settings, policy_service, query_service, audit_recorder, engine)
