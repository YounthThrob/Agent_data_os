"""Ports owned by structured data ingestion."""

from __future__ import annotations

from typing import Any, Protocol

from agent_data_os.domains.ingestion.models import DataSource, IngestionRun, SyncJob


class IngestionRepository(Protocol):
    def save_data_source(self, source: DataSource) -> None: ...
    def get_data_source(self, tenant_id: str, source_id: str) -> DataSource | None: ...
    def save_sync_job(self, job: SyncJob) -> None: ...
    def get_sync_job(self, tenant_id: str, job_id: str) -> SyncJob | None: ...
    def save_run(self, run: IngestionRun) -> None: ...
    def get_run(self, tenant_id: str, run_id: str) -> IngestionRun | None: ...
    def find_run_by_idempotency_key(
        self, tenant_id: str, job_id: str, idempotency_key: str
    ) -> IngestionRun | None: ...


class SchemaDiscoveryPort(Protocol):
    def test_connection(self, source: DataSource) -> None: ...
    def discover(self, source: DataSource) -> tuple[dict[str, Any], ...]: ...


class IngestionCommitPort(Protocol):
    """Atomically publish a dataset version, serving rows and domain event."""

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
    ) -> IngestionRun: ...
