"""Iteration 2 persistence, isolation and durable-audit integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from agent_data_os.application.query_service import QueryApplicationService
from agent_data_os.core.config import Settings
from agent_data_os.core.context import ActorType, RequestContext, SecurityContext
from agent_data_os.core.errors import AuditUnavailableError
from agent_data_os.domains.audit.models import AuditEvent
from agent_data_os.domains.data_service.models import QueryCommand
from agent_data_os.domains.metadata.models import (
    AgentMetadata,
    DataApiMetadata,
    Tenant,
    UserAccount,
)
from agent_data_os.domains.policy.models import Grant
from agent_data_os.domains.policy.service import PolicyEvaluator
from agent_data_os.infrastructure.memory import InMemoryQueryDataPort
from agent_data_os.infrastructure.persistence.database import (
    build_engine,
    build_session_factory,
    initialize_schema,
    tenant_session,
)
from agent_data_os.infrastructure.persistence.models import AuditOutboxRow, Base
from agent_data_os.infrastructure.persistence.repositories import (
    SqlAlchemyAuditRecorder,
    SqlAlchemyMetadataRepository,
    SqlAlchemyPolicyRepository,
    SqlAlchemyQueryApiRepository,
    new_grant_row,
)


@pytest.fixture()
def persistence():
    settings = Settings(
        environment="test",
        database_url="sqlite:///:memory:",
        database_auto_create=True,
    )
    engine = build_engine(settings)
    initialize_schema(engine, settings)
    sessions = build_session_factory(engine)
    try:
        yield sessions
    finally:
        engine.dispose()


def _published_api(tenant_id: str, *, api_id: str) -> DataApiMetadata:
    return DataApiMetadata(
        id=api_id,
        tenant_id=tenant_id,
        code="receivables",
        name="Receivables",
        api_type="QUERY",
        semantic_version="1.0.0",
        dataset_id="ds_receivables",
        lifecycle_status="PUBLISHED",
        dataset_version=3,
        freshness_at="2026-08-05T00:00:00Z",
        quality_score=98.5,
        contract={
            "selectable_fields": ["customer", "region", "amount"],
            "allowed_filters": {"region": ["eq"]},
            "allowed_order_fields": ["amount"],
            "allowed_purposes": ["collection"],
            "default_limit": 10,
            "maximum_limit": 50,
            "field_types": {"amount": "decimal"},
        },
    )


def test_metadata_repository_prevents_cross_tenant_lookup(persistence) -> None:
    repository = SqlAlchemyMetadataRepository(persistence)
    repository.add_tenant(Tenant("tenant_a", "A", "Tenant A", "CN"))
    repository.add_tenant(Tenant("tenant_b", "B", "Tenant B", "CN"))
    repository.add_user(
        UserAccount("user_a", "tenant_a", "subject-a", "alice", "Alice")
    )
    repository.add_agent(
        AgentMetadata(
            "agent_a",
            "tenant_a",
            "collector",
            "Collector",
            "user_a",
            "SPECIALIST",
            "collection",
            "MEDIUM",
        )
    )
    repository.add_data_api(_published_api("tenant_a", api_id="api_a"))

    assert repository.get_user("tenant_a", "user_a") is not None
    assert repository.get_agent("tenant_a", "agent_a") is not None
    assert repository.get_data_api("tenant_a", "api_a") is not None
    assert repository.get_user("tenant_b", "user_a") is None
    assert repository.get_agent("tenant_b", "agent_a") is None
    assert repository.get_data_api("tenant_b", "api_a") is None


def test_policy_and_query_api_repositories_are_tenant_scoped(persistence) -> None:
    metadata = SqlAlchemyMetadataRepository(persistence)
    metadata.add_data_api(_published_api("tenant_a", api_id="api_a"))
    grant = Grant(
        tenant_id="tenant_a",
        actor_id="agent_a",
        resource_type="DATA_API_VERSION",
        resource_id="receivables:1.0.0",
        action="INVOKE",
        purposes=frozenset({"collection"}),
        max_rows=5,
    )
    with tenant_session(persistence, "tenant_a") as session:
        session.add(new_grant_row(tenant_id="tenant_a", grant=grant))

    api_repository = SqlAlchemyQueryApiRepository(persistence)
    assert api_repository.get_published("tenant_a", "receivables") is not None
    assert api_repository.get_published("tenant_b", "receivables") is None

    context = SecurityContext(
        "tenant_a", ActorType.AGENT, "agent_a", "collection"
    )
    from agent_data_os.domains.policy.models import DecisionRequest, Resource

    request = DecisionRequest(
        context, Resource("DATA_API_VERSION", "receivables:1.0.0"), "INVOKE", "test"
    )
    assert len(SqlAlchemyPolicyRepository(persistence).find_grants(request)) == 1


def test_query_execution_writes_sanitized_success_outbox(persistence) -> None:
    metadata = SqlAlchemyMetadataRepository(persistence)
    metadata.add_data_api(_published_api("tenant_a", api_id="api_a"))
    grant = Grant(
        tenant_id="tenant_a",
        actor_id="agent_a",
        resource_type="DATA_API_VERSION",
        resource_id="receivables:1.0.0",
        action="INVOKE",
        purposes=frozenset({"collection"}),
        max_rows=5,
    )
    with tenant_session(persistence, "tenant_a") as session:
        session.add(new_grant_row(tenant_id="tenant_a", grant=grant))

    service = QueryApplicationService(
        SqlAlchemyQueryApiRepository(persistence),
        InMemoryQueryDataPort(
            {
                ("tenant_a", "ds_receivables"): [
                    {"customer": "Sensitive Customer", "region": "EAST", "amount": 9}
                ]
            }
        ),
        PolicyEvaluator(SqlAlchemyPolicyRepository(persistence)),
        SqlAlchemyAuditRecorder(persistence),
    )
    context = RequestContext(
        "req_1",
        "trace_1",
        SecurityContext("tenant_a", ActorType.AGENT, "agent_a", "collection"),
        "test",
    )
    result = service.execute(
        context,
        QueryCommand("receivables", "1.0.0", ("customer", "amount"), (), (), 10),
    )

    assert len(result.rows) == 1
    with tenant_session(persistence, "tenant_a") as session:
        row = session.scalar(select(AuditOutboxRow))
        assert row is not None
        assert row.outcome == "SUCCESS"
        assert row.status == "PENDING"
        assert len(row.payload_hash) == 64
        serialized = str(row.payload_json)
        assert "Sensitive Customer" not in serialized
        assert "filters" not in serialized


def test_audit_recorder_failure_is_fail_closed() -> None:
    class UnavailableRecorder:
        def record(self, event: AuditEvent) -> None:
            raise AuditUnavailableError()

    # A missing API creates a denied audit attempt; audit failure replaces the
    # original response so callers cannot infer protected state without logging.
    from agent_data_os.infrastructure.memory import (
        InMemoryPolicyRepository,
        InMemoryQueryApiRepository,
    )

    service = QueryApplicationService(
        InMemoryQueryApiRepository(),
        InMemoryQueryDataPort(),
        PolicyEvaluator(InMemoryPolicyRepository()),
        UnavailableRecorder(),
    )
    context = RequestContext(
        "req_1",
        "trace_1",
        SecurityContext("tenant_a", ActorType.AGENT, "agent_a", "collection"),
        "test",
    )
    with pytest.raises(AuditUnavailableError):
        service.execute(
            context, QueryCommand("hidden", "1.0.0", ("id",), (), (), 10)
        )


def test_initial_migration_enables_postgresql_rls() -> None:
    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "20260805_0001_iteration2_metadata_audit.py"
    ).read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "current_setting('app.current_tenant', true)" in migration
    assert "audit_outbox" in migration


def test_runtime_requirements_are_version_pinned() -> None:
    requirements = (
        Path(__file__).parents[1] / "requirements.txt"
    ).read_text(encoding="utf-8")
    for dependency in ("fastapi", "SQLAlchemy", "alembic", "psycopg[binary]"):
        line = next(line for line in requirements.splitlines() if line.startswith(dependency))
        assert "==" in line
