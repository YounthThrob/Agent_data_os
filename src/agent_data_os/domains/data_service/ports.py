"""Ports owned by the data service domain."""

from __future__ import annotations

from typing import Any, Protocol

from agent_data_os.domains.data_service.models import (
    OrderBy,
    QueryApiDefinition,
    QueryFilter,
)


class QueryApiRepository(Protocol):
    def get_published(self, tenant_id: str, api_code: str) -> QueryApiDefinition | None:
        ...


class QueryDataPort(Protocol):
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
        ...

