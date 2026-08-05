"""In-memory adapters used only for local development and automated tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from agent_data_os.domains.data_service.models import (
    OrderBy,
    QueryApiDefinition,
    QueryFilter,
)
from agent_data_os.domains.policy.models import DecisionRequest, Grant


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

