"""Data-source and ingestion-run aggregates with explicit state transitions."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from agent_data_os.core.errors import InvalidStateTransitionError


class DataSourceStatus(str, Enum):
    DRAFT = "DRAFT"
    TESTED = "TESTED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class SyncJobStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class RunStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class DataSource:
    id: str
    tenant_id: str
    name: str
    source_type: str
    connector_version: str
    connection: dict[str, Any]
    secret_ref: str
    owner_id: str
    status: DataSourceStatus = DataSourceStatus.DRAFT
    discovered_schema: tuple[dict[str, Any], ...] = ()
    version: int = 1

    def mark_tested(self) -> "DataSource":
        if self.status is DataSourceStatus.ARCHIVED:
            raise InvalidStateTransitionError("data source cannot be tested in this state")
        next_status = (
            DataSourceStatus.ACTIVE
            if self.status is DataSourceStatus.ACTIVE
            else DataSourceStatus.TESTED
        )
        return replace(self, status=next_status, version=self.version + 1)

    def activate(self) -> "DataSource":
        if self.status is not DataSourceStatus.TESTED:
            raise InvalidStateTransitionError("only a tested data source can be activated")
        return replace(self, status=DataSourceStatus.ACTIVE, version=self.version + 1)

    def with_schema(self, objects: tuple[dict[str, Any], ...]) -> "DataSource":
        if self.status not in {DataSourceStatus.TESTED, DataSourceStatus.ACTIVE}:
            raise InvalidStateTransitionError("data source must be tested before discovery")
        return replace(self, discovered_schema=objects, version=self.version + 1)


@dataclass(frozen=True, slots=True)
class SyncJob:
    id: str
    tenant_id: str
    name: str
    data_source_id: str
    source_objects: tuple[dict[str, Any], ...]
    sync_mode: str
    target_dataset_name: str
    schedule: dict[str, Any] = field(default_factory=dict)
    incremental: dict[str, Any] = field(default_factory=dict)
    status: SyncJobStatus = SyncJobStatus.ACTIVE
    version: int = 1


@dataclass(frozen=True, slots=True)
class IngestionRun:
    id: str
    tenant_id: str
    sync_job_id: str
    idempotency_key: str
    status: RunStatus = RunStatus.QUEUED
    checkpoint: dict[str, Any] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)
    result_hash: str | None = None
    dataset_version_id: str | None = None
    error_code: str | None = None
    row_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def start(self) -> "IngestionRun":
        if self.status not in {RunStatus.QUEUED, RunStatus.FAILED}:
            raise InvalidStateTransitionError("run cannot start from its current state")
        return replace(
            self, status=RunStatus.RUNNING, started_at=datetime.now(timezone.utc)
        )

    def complete(
        self,
        *,
        result_hash: str,
        checkpoint: dict[str, Any],
        manifest: dict[str, Any],
        dataset_version_id: str,
        row_count: int,
    ) -> "IngestionRun":
        if self.status is not RunStatus.RUNNING:
            raise InvalidStateTransitionError("only a running ingestion can complete")
        return replace(
            self,
            status=RunStatus.SUCCEEDED,
            result_hash=result_hash,
            checkpoint=checkpoint,
            manifest=manifest,
            dataset_version_id=dataset_version_id,
            row_count=row_count,
            completed_at=datetime.now(timezone.utc),
        )

    def fail(self, error_code: str, checkpoint: dict[str, Any]) -> "IngestionRun":
        if self.status is not RunStatus.RUNNING:
            raise InvalidStateTransitionError("only a running ingestion can fail")
        return replace(
            self,
            status=RunStatus.FAILED,
            error_code=error_code,
            checkpoint=checkpoint,
            completed_at=datetime.now(timezone.utc),
        )

    def quarantine(
        self,
        error_code: str,
        checkpoint: dict[str, Any],
        manifest: dict[str, Any],
    ) -> "IngestionRun":
        if self.status is not RunStatus.RUNNING:
            raise InvalidStateTransitionError("only a running ingestion can quarantine")
        return replace(
            self,
            status=RunStatus.QUARANTINED,
            error_code=error_code,
            checkpoint=checkpoint,
            manifest=manifest,
            completed_at=datetime.now(timezone.utc),
        )

    def request_cancel(self) -> "IngestionRun":
        if self.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
            raise InvalidStateTransitionError("run cannot be cancelled in this state")
        return replace(self, status=RunStatus.CANCEL_REQUESTED)
