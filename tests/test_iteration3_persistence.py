"""Transactional ingestion, Serving and outbox relay integration tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy import create_engine, text

from agent_data_os.core.config import Settings
from agent_data_os.domains.audit.models import AuditEvent
from agent_data_os.domains.data_service.models import OrderBy, QueryFilter
from agent_data_os.domains.ingestion.models import IngestionRun
from agent_data_os.domains.ingestion.models import SyncJob
from agent_data_os.application.ingestion_service import IngestionApplicationService
from agent_data_os.core.context import ActorType, RequestContext, SecurityContext
from agent_data_os.infrastructure.connectors import DevelopmentSchemaDiscovery
from agent_data_os.infrastructure.memory import InMemoryIngestionStore
from agent_data_os.infrastructure.outbox import SqlAlchemyOutboxRelay
from agent_data_os.infrastructure.connectors import (
    RejectingSecretResolver,
    SqlAlchemySchemaDiscovery,
)
from agent_data_os.domains.ingestion.models import DataSource
from agent_data_os.infrastructure.persistence.database import (
    build_engine,
    build_session_factory,
    initialize_schema,
    tenant_session,
)
from agent_data_os.infrastructure.persistence.ingestion import (
    SqlAlchemyIngestionCommitter,
    SqlAlchemyServingQueryDataPort,
)
from agent_data_os.infrastructure.persistence.models import (
    AuditOutboxRow,
    DatasetRow,
    DatasetVersionRow,
    DomainOutboxRow,
)
from agent_data_os.infrastructure.persistence.repositories import SqlAlchemyAuditRecorder


@pytest.fixture()
def sessions():
    settings = Settings(
        environment="test",
        database_url="sqlite:///:memory:",
        database_auto_create=True,
    )
    engine = build_engine(settings)
    initialize_schema(engine, settings)
    factory = build_session_factory(engine)
    try:
        yield factory
    finally:
        engine.dispose()


def _running_run() -> IngestionRun:
    return IngestionRun(
        id="run_1",
        tenant_id="tenant_a",
        sync_job_id="job_1",
        idempotency_key="once",
    ).start()


def test_ingestion_commit_is_atomic_and_serving_is_tenant_scoped(sessions) -> None:
    run = _running_run()
    from agent_data_os.infrastructure.persistence.ingestion import (
        SqlAlchemyIngestionRepository,
    )

    repository = SqlAlchemyIngestionRepository(sessions)
    repository.save_run(run)
    committer = SqlAlchemyIngestionCommitter(sessions)
    completed = committer.commit_success(
        run=run,
        dataset_name="crm.customers",
        result_hash="b" * 64,
        checkpoint={"offset": 2},
        manifest={
            "row_count": 2,
            "content_hash": "b" * 64,
            "quality_status": "PASS",
        },
        schema=({"name": "id", "type": "integer"},),
        rows=(
            {"id": 1, "region": "EAST", "amount": 10},
            {"id": 2, "region": "WEST", "amount": 20},
        ),
    )
    assert completed.status.value == "SUCCEEDED"

    with tenant_session(sessions, "tenant_a") as session:
        dataset = session.scalar(select(DatasetRow))
        version = session.scalar(select(DatasetVersionRow))
        event = session.scalar(select(DomainOutboxRow))
        assert dataset is not None and dataset.active_version_id == version.id
        assert version.row_count == 2
        assert event is not None and event.status == "PENDING"

    serving = SqlAlchemyServingQueryDataPort(sessions)
    rows = serving.query(
        tenant_id="tenant_a",
        dataset_id=dataset.id,
        selected_fields=("id", "amount"),
        filters=(QueryFilter("region", "eq", "EAST"),),
        order_by=(OrderBy("amount", "desc"),),
        limit=10,
    )
    assert rows == [{"id": 1, "amount": 10}]
    assert (
        serving.query(
            tenant_id="tenant_b",
            dataset_id=dataset.id,
            selected_fields=("id",),
            filters=(),
            order_by=(),
            limit=10,
        )
        == []
    )


def test_repository_updates_preserve_creation_metadata(sessions) -> None:
    from agent_data_os.infrastructure.persistence.ingestion import (
        SqlAlchemyIngestionRepository,
    )

    repository = SqlAlchemyIngestionRepository(sessions)
    source = DataSource(
        id="source_1",
        tenant_id="tenant_a",
        name="CRM",
        source_type="POSTGRESQL",
        connector_version="postgresql-1.0",
        connection={"host": "db", "port": 5432, "database": "crm"},
        secret_ref="vault://tenant-a/crm",
        owner_id="admin",
    )
    repository.save_data_source(source)
    repository.save_data_source(source.mark_tested())
    persisted = repository.get_data_source("tenant_a", "source_1")
    assert persisted is not None
    assert persisted.status.value == "TESTED"
    assert persisted.version == 2


def test_invalid_manifest_rolls_back_everything(sessions) -> None:
    run = _running_run()
    from agent_data_os.infrastructure.persistence.ingestion import (
        SqlAlchemyIngestionRepository,
    )

    SqlAlchemyIngestionRepository(sessions).save_run(run)
    with pytest.raises(Exception, match="row_count"):
        SqlAlchemyIngestionCommitter(sessions).commit_success(
            run=run,
            dataset_name="crm.customers",
            result_hash="c" * 64,
            checkpoint={},
            manifest={
                "row_count": 2,
                "content_hash": "c" * 64,
                "quality_status": "PASS",
            },
            schema=(),
            rows=({"id": 1},),
        )
    with tenant_session(sessions, "tenant_a") as session:
        assert session.scalar(select(DatasetRow)) is None
        assert session.scalar(select(DomainOutboxRow)) is None


def test_failed_quality_gate_quarantines_without_serving_publish(sessions) -> None:
    run = _running_run()
    from agent_data_os.infrastructure.persistence.ingestion import (
        SqlAlchemyIngestionRepository,
    )

    SqlAlchemyIngestionRepository(sessions).save_run(run)
    quarantined = SqlAlchemyIngestionCommitter(sessions).commit_success(
        run=run,
        dataset_name="crm.customers",
        result_hash="d" * 64,
        checkpoint={"offset": 1},
        manifest={
            "row_count": 1,
            "content_hash": "d" * 64,
            "quality_status": "FAIL",
        },
        schema=(),
        rows=({"id": 1},),
    )
    assert quarantined.status.value == "QUARANTINED"
    assert quarantined.error_code == "QUALITY_GATE_FAILED"
    with tenant_session(sessions, "tenant_a") as session:
        assert session.scalar(select(DatasetRow)) is None
        event = session.scalar(select(DomainOutboxRow))
        assert event.event_type == "IngestionRunQuarantined"


def test_outbox_relay_marks_success_and_retries_safely(sessions) -> None:
    audit = AuditEvent.create(
        tenant_id="tenant_a",
        trace_id="trace_1",
        actor_type="AGENT",
        actor_id="agent_a",
        action="QUERY",
        resource_type="DATA_API",
        resource_id="api_1",
        purpose="collection",
        outcome="SUCCESS",
    )
    SqlAlchemyAuditRecorder(sessions).record(audit)

    class Publisher:
        def __init__(self) -> None:
            self.events: list[tuple[str, str]] = []

        def publish(self, topic: str, key: str, payload: dict) -> None:
            self.events.append((topic, key))

    publisher = Publisher()
    relay = SqlAlchemyOutboxRelay(sessions, publisher)
    assert relay.relay_audit("tenant_a") == 1
    assert relay.relay_audit("tenant_a") == 0
    with tenant_session(sessions, "tenant_a") as session:
        row = session.scalar(select(AuditOutboxRow))
        assert row.status == "PUBLISHED"
        assert row.attempts == 1
        assert row.published_at is not None


def test_outbox_failure_stores_only_error_fingerprint(sessions) -> None:
    SqlAlchemyAuditRecorder(sessions).record(
        AuditEvent.create(
            tenant_id="tenant_a",
            trace_id="trace_2",
            actor_type="AGENT",
            actor_id="agent_a",
            action="QUERY",
            resource_type="DATA_API",
            resource_id="api_1",
            purpose="collection",
            outcome="SUCCESS",
        )
    )

    class FailingPublisher:
        def publish(self, topic: str, key: str, payload: dict) -> None:
            raise RuntimeError("broker-password-should-not-be-stored")

    assert SqlAlchemyOutboxRelay(sessions, FailingPublisher()).relay_audit("tenant_a") == 0
    with tenant_session(sessions, "tenant_a") as session:
        row = session.scalar(select(AuditOutboxRow))
        assert row.status == "PENDING"
        assert row.attempts == 1
        assert len(row.last_error_code) == 16
        assert "password" not in row.last_error_code


def test_sqlalchemy_connector_discovers_schema_without_exposing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector = SqlAlchemySchemaDiscovery(RejectingSecretResolver())

    def engine_factory(source: DataSource):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
            )
        return engine

    monkeypatch.setattr(connector, "_engine", engine_factory)
    source = DataSource(
        id="source_1",
        tenant_id="tenant_a",
        name="CRM",
        source_type="POSTGRESQL",
        connector_version="postgresql-1.0",
        connection={"host": "hidden", "port": 5432, "database": "crm"},
        secret_ref="vault://tenant-a/crm",
        owner_id="admin",
    )
    connector.test_connection(source)
    objects = connector.discover(source)
    assert objects[0]["object"] == "customers"
    assert objects[0]["primary_key"] == ["id"]
    assert "vault://" not in str(objects)


def test_iteration3_migration_enables_rls_for_every_new_tenant_table() -> None:
    from pathlib import Path

    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "20260805_0002_iteration3_ingestion_serving.py"
    ).read_text(encoding="utf-8")
    for table in (
        "data_sources",
        "sync_jobs",
        "ingestion_runs",
        "datasets",
        "dataset_versions",
        "serving_rows",
        "domain_outbox",
    ):
        assert f'"{table}"' in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration


def test_failed_run_retries_from_checkpoint_and_cancel_is_explicit() -> None:
    store = InMemoryIngestionStore()
    service = IngestionApplicationService(
        store, DevelopmentSchemaDiscovery(), store
    )
    context = RequestContext(
        "req_1",
        "trace_1",
        SecurityContext("tenant_a", ActorType.USER, "admin", "ingestion"),
        "TEST",
    )
    store.save_sync_job(
        SyncJob(
            id="job_1",
            tenant_id="tenant_a",
            name="Job",
            data_source_id="source_1",
            source_objects=({"object": "customers"},),
            sync_mode="FULL",
            target_dataset_name="crm.customers",
        )
    )
    failed = IngestionRun(
        id="run_failed",
        tenant_id="tenant_a",
        sync_job_id="job_1",
        idempotency_key="initial",
    ).start().fail("SOURCE_TIMEOUT", {"offset": 99})
    store.save_run(failed)

    retry = service.retry_run(context, failed.id, "retry-1")
    assert retry.status.value == "RUNNING"
    assert retry.checkpoint == {"offset": 99}
    assert service.retry_run(context, failed.id, "retry-1").id == retry.id
    cancelled = service.cancel_run(context, retry.id)
    assert cancelled.status.value == "CANCEL_REQUESTED"
