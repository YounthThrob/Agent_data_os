"""Query API definitions and logical query values."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_OPERATORS = frozenset({"eq", "neq", "gt", "gte", "lt", "lte", "in"})


@dataclass(frozen=True, slots=True)
class QueryFilter:
    field: str
    operator: str
    value: Any
    immutable: bool = False


@dataclass(frozen=True, slots=True)
class OrderBy:
    field: str
    direction: str = "asc"


@dataclass(frozen=True, slots=True)
class QueryApiDefinition:
    code: str
    version: str
    dataset_id: str
    selectable_fields: frozenset[str]
    allowed_filters: dict[str, frozenset[str]]
    allowed_order_fields: frozenset[str]
    allowed_purposes: frozenset[str]
    default_limit: int
    maximum_limit: int
    dataset_version: int
    freshness_at: str
    quality_score: float
    field_types: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QueryCommand:
    api_code: str
    api_version: str
    selected_fields: tuple[str, ...]
    filters: tuple[QueryFilter, ...]
    order_by: tuple[OrderBy, ...]
    limit: int | None


@dataclass(frozen=True, slots=True)
class QueryResult:
    rows: tuple[dict[str, Any], ...]
    schema: tuple[dict[str, Any], ...]
    dataset_version: int
    freshness_at: str
    quality_score: float
    decision_id: str
    policy_version: int
    result_limit_applied: int
    truncated: bool

