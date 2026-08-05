"""Application orchestration for the Iteration 3 structured ingestion slice."""

from __future__ import annotations

import re
import uuid
from typing import Any

from agent_data_os.core.context import RequestContext
from agent_data_os.core.errors import (
    InvalidArgumentError,
    InvalidStateTransitionError,
    ResourceNotVisibleError,
)
from agent_data_os.domains.ingestion.models import DataSource, IngestionRun, SyncJob
from agent_data_os.domains.ingestion.ports import (
    IngestionCommitPort,
    IngestionRepository,
    SchemaDiscoveryPort,
)


SECRET_REF_PATTERN = re.compile(r"^(vault|aws-secretsmanager|azure-keyvault)://[^\s]+$")
SUPPORTED_SOURCE_TYPES = frozenset({"POSTGRESQL"})
SUPPORTED_SYNC_MODES = frozenset({"FULL", "INCREMENTAL_TIMESTAMP", "CDC"})


class IngestionApplicationService:
    """Enforce source safety and idempotent ingestion state transitions."""

    def __init__(
        self,
        repository: IngestionRepository,
        connector: SchemaDiscoveryPort,
        commit_port: IngestionCommitPort,
    ) -> None:
        self._repository = repository
        self._connector = connector
        self._commit_port = commit_port

    def create_data_source(
        self,
        context: RequestContext,
        *,
        name: str,
        source_type: str,
        connector_version: str,
        connection: dict[str, Any],
        secret_ref: str,
        owner_id: str,
    ) -> DataSource:
        normalized_type = source_type.upper()
        if normalized_type not in SUPPORTED_SOURCE_TYPES:
            raise InvalidArgumentError("unsupported data source type")
        if not SECRET_REF_PATTERN.fullmatch(secret_ref):
            raise InvalidArgumentError("credential must use an approved secret reference")
        forbidden = {"password", "secret", "token", "username", "user"}
        if forbidden.intersection(key.lower() for key in connection):
            raise InvalidArgumentError("connection metadata must not contain credentials")
        source = DataSource(
            id=f"source_{uuid.uuid4().hex}",
            tenant_id=context.security.tenant_id,
            name=name,
            source_type=normalized_type,
            connector_version=connector_version,
            connection=dict(connection),
            secret_ref=secret_ref,
            owner_id=owner_id,
        )
        self._repository.save_data_source(source)
        return source

    def test_data_source(self, context: RequestContext, source_id: str) -> DataSource:
        source = self._require_source(context, source_id)
        self._connector.test_connection(source)
        tested = source.mark_tested()
        self._repository.save_data_source(tested)
        return tested

    def discover_schema(
        self, context: RequestContext, source_id: str
    ) -> DataSource:
        source = self._require_source(context, source_id)
        objects = self._connector.discover(source)
        discovered = source.with_schema(objects)
        self._repository.save_data_source(discovered)
        return discovered

    def create_sync_job(
        self,
        context: RequestContext,
        *,
        name: str,
        data_source_id: str,
        source_objects: tuple[dict[str, Any], ...],
        sync_mode: str,
        target_dataset_name: str,
        schedule: dict[str, Any],
        incremental: dict[str, Any],
    ) -> SyncJob:
        source = self._require_source(context, data_source_id)
        if source.status.value not in {"TESTED", "ACTIVE"}:
            raise InvalidStateTransitionError(
                "sync job requires a successfully tested data source"
            )
        normalized_mode = sync_mode.upper()
        if normalized_mode not in SUPPORTED_SYNC_MODES:
            raise InvalidArgumentError("unsupported sync mode")
        if not source_objects:
            raise InvalidArgumentError("at least one source object is required")
        job = SyncJob(
            id=f"job_{uuid.uuid4().hex}",
            tenant_id=context.security.tenant_id,
            name=name,
            data_source_id=data_source_id,
            source_objects=source_objects,
            sync_mode=normalized_mode,
            target_dataset_name=target_dataset_name,
            schedule=dict(schedule),
            incremental=dict(incremental),
        )
        self._repository.save_sync_job(job)
        return job

    def start_run(
        self, context: RequestContext, job_id: str, idempotency_key: str
    ) -> IngestionRun:
        if not idempotency_key or len(idempotency_key) > 128:
            raise InvalidArgumentError("a valid Idempotency-Key is required")
        job = self._require_job(context, job_id)
        if job.status.value != "ACTIVE":
            raise InvalidStateTransitionError("only an active sync job can run")
        existing = self._repository.find_run_by_idempotency_key(
            context.security.tenant_id, job.id, idempotency_key
        )
        if existing is not None:
            return existing
        run = IngestionRun(
            id=f"run_{uuid.uuid4().hex}",
            tenant_id=context.security.tenant_id,
            sync_job_id=job.id,
            idempotency_key=idempotency_key,
        ).start()
        self._repository.save_run(run)
        return run

    def retry_run(
        self, context: RequestContext, run_id: str, idempotency_key: str
    ) -> IngestionRun:
        previous = self._require_run(context, run_id)
        if previous.status.value not in {"FAILED", "QUARANTINED"}:
            raise InvalidStateTransitionError("only a failed or quarantined run can retry")
        existing = self._repository.find_run_by_idempotency_key(
            context.security.tenant_id, previous.sync_job_id, idempotency_key
        )
        if existing is not None:
            return existing
        retry = IngestionRun(
            id=f"run_{uuid.uuid4().hex}",
            tenant_id=context.security.tenant_id,
            sync_job_id=previous.sync_job_id,
            idempotency_key=idempotency_key,
            checkpoint=previous.checkpoint,
        ).start()
        self._repository.save_run(retry)
        return retry

    def cancel_run(self, context: RequestContext, run_id: str) -> IngestionRun:
        cancelled = self._require_run(context, run_id).request_cancel()
        self._repository.save_run(cancelled)
        return cancelled

    def fail_run(
        self,
        context: RequestContext,
        run_id: str,
        *,
        error_code: str,
        checkpoint: dict[str, Any],
    ) -> IngestionRun:
        if not error_code or len(error_code) > 64:
            raise InvalidArgumentError("a stable error_code is required")
        failed = self._require_run(context, run_id).fail(error_code, checkpoint)
        self._repository.save_run(failed)
        return failed

    def complete_run(
        self,
        context: RequestContext,
        run_id: str,
        *,
        result_hash: str,
        checkpoint: dict[str, Any],
        manifest: dict[str, Any],
        schema: tuple[dict[str, Any], ...],
        rows: tuple[dict[str, Any], ...],
    ) -> IngestionRun:
        run = self._require_run(context, run_id)
        if run.status.value == "SUCCEEDED" and run.result_hash == result_hash:
            return run
        if manifest.get("row_count") != len(rows):
            raise InvalidArgumentError("manifest row_count does not match the payload")
        if manifest.get("content_hash") != result_hash:
            raise InvalidArgumentError(
                "manifest content_hash does not match result_hash"
            )
        job = self._require_job(context, run.sync_job_id)
        return self._commit_port.commit_success(
            run=run,
            dataset_name=job.target_dataset_name,
            result_hash=result_hash,
            checkpoint=checkpoint,
            manifest=manifest,
            schema=schema,
            rows=rows,
        )

    def get_run(self, context: RequestContext, run_id: str) -> IngestionRun:
        return self._require_run(context, run_id)

    def _require_source(self, context: RequestContext, source_id: str) -> DataSource:
        source = self._repository.get_data_source(
            context.security.tenant_id, source_id
        )
        if source is None:
            raise ResourceNotVisibleError()
        return source

    def _require_job(self, context: RequestContext, job_id: str) -> SyncJob:
        job = self._repository.get_sync_job(context.security.tenant_id, job_id)
        if job is None:
            raise ResourceNotVisibleError()
        return job

    def _require_run(self, context: RequestContext, run_id: str) -> IngestionRun:
        run = self._repository.get_run(context.security.tenant_id, run_id)
        if run is None:
            raise ResourceNotVisibleError()
        return run
