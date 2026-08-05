"""SQLAlchemy ingestion, catalog and Serving PostgreSQL adapters."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from agent_data_os.core.errors import ConflictError, InvalidArgumentError
from agent_data_os.domains.data_service.models import OrderBy, QueryFilter
from agent_data_os.domains.ingestion.models import (
    DataSource,
    DataSourceStatus,
    IngestionRun,
    RunStatus,
    SyncJob,
    SyncJobStatus,
)
from agent_data_os.infrastructure.persistence.database import tenant_session
from agent_data_os.infrastructure.persistence.models import (
    DataSourceRow,
    DatasetRow,
    DatasetVersionRow,
    DomainOutboxRow,
    IngestionRunRow,
    ServingRow,
    SyncJobRow,
    utc_now,
)


class SqlAlchemyIngestionRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def save_data_source(self, source: DataSource) -> None:
        with tenant_session(self._sessions, source.tenant_id) as session:
            row = session.scalar(
                select(DataSourceRow).where(
                    DataSourceRow.tenant_id == source.tenant_id,
                    DataSourceRow.id == source.id,
                )
            )
            if row is None:
                row = DataSourceRow(
                    id=source.id,
                    tenant_id=source.tenant_id,
                )
                session.add(row)
            row.name = source.name
            row.source_type = source.source_type
            row.connector_version = source.connector_version
            row.connection_json = source.connection
            row.secret_ref = source.secret_ref
            row.owner_id = source.owner_id
            row.status = source.status.value
            row.discovered_schema_json = list(source.discovered_schema)
            row.version = source.version
            row.updated_at = utc_now()

    def get_data_source(self, tenant_id: str, source_id: str) -> DataSource | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(DataSourceRow).where(
                    DataSourceRow.tenant_id == tenant_id,
                    DataSourceRow.id == source_id,
                )
            )
            return None if row is None else self._to_source(row)

    def save_sync_job(self, job: SyncJob) -> None:
        with tenant_session(self._sessions, job.tenant_id) as session:
            row = session.scalar(
                select(SyncJobRow).where(
                    SyncJobRow.tenant_id == job.tenant_id, SyncJobRow.id == job.id
                )
            )
            if row is None:
                row = SyncJobRow(
                    id=job.id,
                    tenant_id=job.tenant_id,
                )
                session.add(row)
            row.name = job.name
            row.data_source_id = job.data_source_id
            row.source_objects_json = list(job.source_objects)
            row.sync_mode = job.sync_mode
            row.target_dataset_name = job.target_dataset_name
            row.schedule_json = job.schedule
            row.incremental_json = job.incremental
            row.status = job.status.value
            row.version = job.version
            row.updated_at = utc_now()

    def get_sync_job(self, tenant_id: str, job_id: str) -> SyncJob | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(SyncJobRow).where(
                    SyncJobRow.tenant_id == tenant_id, SyncJobRow.id == job_id
                )
            )
            return None if row is None else self._to_job(row)

    def save_run(self, run: IngestionRun) -> None:
        with tenant_session(self._sessions, run.tenant_id) as session:
            row = session.scalar(
                select(IngestionRunRow).where(
                    IngestionRunRow.tenant_id == run.tenant_id,
                    IngestionRunRow.id == run.id,
                )
            )
            if row is None:
                row = IngestionRunRow(
                    id=run.id,
                    tenant_id=run.tenant_id,
                    sync_job_id=run.sync_job_id,
                    idempotency_key=run.idempotency_key,
                    status=run.status.value,
                    checkpoint_json=run.checkpoint,
                    manifest_json=run.manifest,
                )
                session.add(row)
            row.status = run.status.value
            row.checkpoint_json = run.checkpoint
            row.manifest_json = run.manifest
            row.result_hash = run.result_hash
            row.dataset_version_id = run.dataset_version_id
            row.error_code = run.error_code
            row.row_count = run.row_count
            row.started_at = run.started_at
            row.completed_at = run.completed_at
            row.updated_at = utc_now()

    def get_run(self, tenant_id: str, run_id: str) -> IngestionRun | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(IngestionRunRow).where(
                    IngestionRunRow.tenant_id == tenant_id,
                    IngestionRunRow.id == run_id,
                )
            )
            return None if row is None else self._to_run(row)

    def find_run_by_idempotency_key(
        self, tenant_id: str, job_id: str, idempotency_key: str
    ) -> IngestionRun | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(IngestionRunRow).where(
                    IngestionRunRow.tenant_id == tenant_id,
                    IngestionRunRow.sync_job_id == job_id,
                    IngestionRunRow.idempotency_key == idempotency_key,
                )
            )
            return None if row is None else self._to_run(row)

    @staticmethod
    def _to_source(row: DataSourceRow) -> DataSource:
        return DataSource(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            source_type=row.source_type,
            connector_version=row.connector_version,
            connection=dict(row.connection_json),
            secret_ref=row.secret_ref,
            owner_id=row.owner_id,
            status=DataSourceStatus(row.status),
            discovered_schema=tuple(row.discovered_schema_json),
            version=row.version,
        )

    @staticmethod
    def _to_job(row: SyncJobRow) -> SyncJob:
        return SyncJob(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            data_source_id=row.data_source_id,
            source_objects=tuple(row.source_objects_json),
            sync_mode=row.sync_mode,
            target_dataset_name=row.target_dataset_name,
            schedule=dict(row.schedule_json),
            incremental=dict(row.incremental_json),
            status=SyncJobStatus(row.status),
            version=row.version,
        )

    @staticmethod
    def _to_run(row: IngestionRunRow) -> IngestionRun:
        return IngestionRun(
            id=row.id,
            tenant_id=row.tenant_id,
            sync_job_id=row.sync_job_id,
            idempotency_key=row.idempotency_key,
            status=RunStatus(row.status),
            checkpoint=dict(row.checkpoint_json),
            manifest=dict(row.manifest_json),
            result_hash=row.result_hash,
            dataset_version_id=row.dataset_version_id,
            error_code=row.error_code,
            row_count=row.row_count,
            started_at=row.started_at,
            completed_at=row.completed_at,
        )


class SqlAlchemyIngestionCommitter:
    """Commit the run, catalog version, serving rows and event atomically."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def commit_success(
        self,
        *,
        run: IngestionRun,
        dataset_name: str,
        result_hash: str,
        checkpoint: dict[str, Any],
        manifest: dict[str, Any],
        schema: tuple[dict[str, Any], ...],
        rows: tuple[dict[str, Any], ...],
    ) -> IngestionRun:
        if manifest.get("row_count") != len(rows):
            raise InvalidArgumentError("manifest row_count does not match the payload")
        if manifest.get("content_hash") != result_hash:
            raise InvalidArgumentError("manifest content_hash does not match result_hash")

        with tenant_session(self._sessions, run.tenant_id) as session:
            persisted_run = session.scalar(
                select(IngestionRunRow)
                .where(
                    IngestionRunRow.tenant_id == run.tenant_id,
                    IngestionRunRow.id == run.id,
                )
                .with_for_update()
            )
            if persisted_run is None:
                raise ConflictError("ingestion run no longer exists")
            if persisted_run.status == RunStatus.SUCCEEDED.value:
                if persisted_run.result_hash != result_hash:
                    raise ConflictError("run was already completed with another result")
                return SqlAlchemyIngestionRepository._to_run(persisted_run)

            if manifest.get("quality_status") != "PASS":
                quarantined = run.quarantine(
                    "QUALITY_GATE_FAILED", checkpoint, manifest
                )
                persisted_run.status = quarantined.status.value
                persisted_run.checkpoint_json = checkpoint
                persisted_run.manifest_json = manifest
                persisted_run.error_code = quarantined.error_code
                persisted_run.completed_at = quarantined.completed_at
                persisted_run.updated_at = utc_now()
                session.add(
                    DomainOutboxRow(
                        event_id=f"event_{uuid.uuid4().hex}",
                        tenant_id=run.tenant_id,
                        topic="ingestion.run.quarantined.v1",
                        event_type="IngestionRunQuarantined",
                        aggregate_id=run.id,
                        payload_json={
                            "run_id": run.id,
                            "error_code": "QUALITY_GATE_FAILED",
                        },
                    )
                )
                return quarantined

            dataset = session.scalar(
                select(DatasetRow)
                .where(
                    DatasetRow.tenant_id == run.tenant_id,
                    DatasetRow.logical_name == dataset_name,
                )
                .with_for_update()
            )
            if dataset is None:
                dataset = DatasetRow(
                    id=f"dataset_{uuid.uuid4().hex}",
                    tenant_id=run.tenant_id,
                    logical_name=dataset_name,
                    status="PUBLISHED",
                )
                session.add(dataset)
                session.flush()
                version_number = 1
            else:
                version_number = (
                    session.scalar(
                        select(func.max(DatasetVersionRow.version_number)).where(
                            DatasetVersionRow.tenant_id == run.tenant_id,
                            DatasetVersionRow.dataset_id == dataset.id,
                        )
                    )
                    or 0
                ) + 1

            version_id = f"dataset_version_{uuid.uuid4().hex}"
            session.add(
                DatasetVersionRow(
                    id=version_id,
                    tenant_id=run.tenant_id,
                    dataset_id=dataset.id,
                    version_number=version_number,
                    schema_json=list(schema),
                    manifest_json=manifest,
                    checkpoint_json=checkpoint,
                    row_count=len(rows),
                    content_hash=result_hash,
                    status="PUBLISHED",
                )
            )
            for index, item in enumerate(rows):
                canonical = json.dumps(
                    item, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")
                row_hash = hashlib.sha256(canonical).hexdigest()
                session.add(
                    ServingRow(
                        id=f"serving_{uuid.uuid4().hex}",
                        tenant_id=run.tenant_id,
                        dataset_id=dataset.id,
                        dataset_version_id=version_id,
                        row_key=f"{index}:{row_hash}",
                        data_json=item,
                    )
                )
            dataset.active_version_id = version_id
            dataset.status = "PUBLISHED"
            dataset.version += 1
            dataset.updated_at = utc_now()

            completed = run.complete(
                result_hash=result_hash,
                checkpoint=checkpoint,
                manifest=manifest,
                dataset_version_id=version_id,
                row_count=len(rows),
            )
            persisted_run.status = completed.status.value
            persisted_run.checkpoint_json = checkpoint
            persisted_run.manifest_json = manifest
            persisted_run.result_hash = result_hash
            persisted_run.dataset_version_id = version_id
            persisted_run.row_count = len(rows)
            persisted_run.completed_at = completed.completed_at
            persisted_run.updated_at = utc_now()
            session.add(
                DomainOutboxRow(
                    event_id=f"event_{uuid.uuid4().hex}",
                    tenant_id=run.tenant_id,
                    topic="ingestion.dataset-version.ready.v1",
                    event_type="DatasetVersionReady",
                    aggregate_id=dataset.id,
                    payload_json={
                        "run_id": run.id,
                        "dataset_id": dataset.id,
                        "dataset_version_id": version_id,
                        "version_number": version_number,
                        "row_count": len(rows),
                        "content_hash": result_hash,
                    },
                )
            )
            return completed


class SqlAlchemyServingQueryDataPort:
    """Read only from the currently published immutable dataset version."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def query(
        self,
        *,
        tenant_id: str,
        dataset_id: str,
        selected_fields: tuple[str, ...],
        filters: tuple[QueryFilter, ...],
        order_by: tuple[OrderBy, ...],
        limit: int,
    ) -> list[dict[str, Any]]:
        with tenant_session(self._sessions, tenant_id) as session:
            dataset = session.scalar(
                select(DatasetRow).where(
                    DatasetRow.tenant_id == tenant_id,
                    DatasetRow.id == dataset_id,
                    DatasetRow.status == "PUBLISHED",
                )
            )
            if dataset is None or dataset.active_version_id is None:
                return []
            values = session.scalars(
                select(ServingRow).where(
                    ServingRow.tenant_id == tenant_id,
                    ServingRow.dataset_id == dataset_id,
                    ServingRow.dataset_version_id == dataset.active_version_id,
                )
            ).all()
            rows = [dict(value.data_json) for value in values]

        for query_filter in filters:
            rows = [row for row in rows if self._matches(row, query_filter)]
        for order in reversed(order_by):
            rows.sort(
                key=lambda row: (row.get(order.field) is None, row.get(order.field)),
                reverse=order.direction == "desc",
            )
        return [
            {field: row.get(field) for field in selected_fields}
            for row in rows[:limit]
        ]

    @staticmethod
    def _matches(row: dict[str, Any], item: QueryFilter) -> bool:
        current = row.get(item.field)
        value = item.value
        operations = {
            "eq": lambda: current == value,
            "neq": lambda: current != value,
            "gt": lambda: current is not None and current > value,
            "gte": lambda: current is not None and current >= value,
            "lt": lambda: current is not None and current < value,
            "lte": lambda: current is not None and current <= value,
            "in": lambda: current in value,
        }
        return bool(operations[item.operator]())
