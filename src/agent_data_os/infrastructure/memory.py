"""In-memory adapters used only for local development and automated tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
import uuid

from agent_data_os.domains.audit.models import AuditEvent
from agent_data_os.domains.data_service.models import (
    OrderBy,
    QueryApiDefinition,
    QueryFilter,
)
from agent_data_os.domains.policy.models import DecisionRequest, Grant
from agent_data_os.domains.ingestion.models import DataSource, IngestionRun, SyncJob


class InMemoryPolicyRepository:
    def __init__(self, grants: list[Grant] | None = None) -> None:
        self._grants = list(grants or [])

    def find_grants(self, request: DecisionRequest) -> list[Grant]:
        return [
            grant
            for grant in self._grants
            if grant.tenant_id == request.subject.tenant_id
            and grant.actor_id == request.subject.actor_id
            and grant.resource_type == request.resource.resource_type
            and grant.resource_id == request.resource.resource_id
            and grant.action == request.action
        ]


class InMemoryAuditRecorder:
    """Capture immutable audit events for local development and tests."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


class InMemoryIngestionStore:
    """Local ingestion repository and atomic-commit substitute."""

    def __init__(self) -> None:
        self.sources: dict[tuple[str, str], DataSource] = {}
        self.jobs: dict[tuple[str, str], SyncJob] = {}
        self.runs: dict[tuple[str, str], IngestionRun] = {}
        self.dataset_rows: dict[tuple[str, str], tuple[dict[str, Any], ...]] = {}
        self.events: list[dict[str, Any]] = []

    def save_data_source(self, source: DataSource) -> None:
        self.sources[(source.tenant_id, source.id)] = source

    def get_data_source(self, tenant_id: str, source_id: str) -> DataSource | None:
        return self.sources.get((tenant_id, source_id))

    def save_sync_job(self, job: SyncJob) -> None:
        self.jobs[(job.tenant_id, job.id)] = job

    def get_sync_job(self, tenant_id: str, job_id: str) -> SyncJob | None:
        return self.jobs.get((tenant_id, job_id))

    def save_run(self, run: IngestionRun) -> None:
        self.runs[(run.tenant_id, run.id)] = run

    def get_run(self, tenant_id: str, run_id: str) -> IngestionRun | None:
        return self.runs.get((tenant_id, run_id))

    def find_run_by_idempotency_key(
        self, tenant_id: str, job_id: str, idempotency_key: str
    ) -> IngestionRun | None:
        return next(
            (
                run
                for (stored_tenant, _), run in self.runs.items()
                if stored_tenant == tenant_id
                and run.sync_job_id == job_id
                and run.idempotency_key == idempotency_key
            ),
            None,
        )

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
        if manifest.get("quality_status") != "PASS":
            quarantined = run.quarantine(
                "QUALITY_GATE_FAILED", checkpoint, manifest
            )
            self.save_run(quarantined)
            self.events.append(
                {
                    "event_type": "IngestionRunQuarantined",
                    "run_id": run.id,
                }
            )
            return quarantined
        version_id = f"dataset_version_{uuid.uuid4().hex}"
        completed = run.complete(
            result_hash=result_hash,
            checkpoint=checkpoint,
            manifest=manifest,
            dataset_version_id=version_id,
            row_count=len(rows),
        )
        self.save_run(completed)
        self.dataset_rows[(run.tenant_id, dataset_name)] = deepcopy(rows)
        self.events.append(
            {
                "event_type": "DatasetVersionReady",
                "run_id": run.id,
                "dataset_version_id": version_id,
                "schema": deepcopy(schema),
            }
        )
        return completed


class InMemoryQueryApiRepository:
    def __init__(
        self, definitions: dict[tuple[str, str], QueryApiDefinition] | None = None
    ) -> None:
        self._definitions = dict(definitions or {})

    def get_published(self, tenant_id: str, api_code: str) -> QueryApiDefinition | None:
        return self._definitions.get((tenant_id, api_code))


class InMemoryQueryDataPort:
    """Execute a restricted logical query over local rows.

    It mirrors the behavior expected from the future Serving PostgreSQL adapter:
    every lookup is tenant-bound and accepts only validated logical fields.
    """

    def __init__(
        self, datasets: dict[tuple[str, str], list[dict[str, Any]]] | None = None
    ) -> None:
        self._datasets = deepcopy(datasets or {})

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
        rows = deepcopy(self._datasets.get((tenant_id, dataset_id), []))
        for query_filter in filters:
            rows = [row for row in rows if self._matches(row, query_filter)]
        # Stable sorting is applied in reverse declaration order so the first
        # requested sort key remains the primary key.
        for order in reversed(order_by):
            rows.sort(
                key=lambda row: (row.get(order.field) is None, row.get(order.field)),
                reverse=order.direction == "desc",
            )
        return [
            {field: row.get(field) for field in selected_fields}
            for row in rows[:limit]
        ]
