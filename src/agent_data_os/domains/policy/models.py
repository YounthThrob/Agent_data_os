"""Policy decision domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent_data_os.core.context import SecurityContext


class DecisionEffect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ALLOW_WITH_OBLIGATIONS = "ALLOW_WITH_OBLIGATIONS"


@dataclass(frozen=True, slots=True)
class Resource:
    resource_type: str
    resource_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    subject: SecurityContext
    resource: Resource
    action: str
    environment: str


@dataclass(frozen=True, slots=True)
class Obligations:
    """Restrictions a policy enforcement point must apply before returning data."""

    row_filters: tuple[tuple[str, str, Any], ...] = ()
    field_masks: tuple[tuple[str, str], ...] = ()
    max_rows: int | None = None
    allow_export: bool = False


@dataclass(frozen=True, slots=True)
class DecisionResult:
    decision_id: str
    effect: DecisionEffect
    policy_version: int
    obligations: Obligations = Obligations()
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Grant:
    """Minimal V1.0 grant used by the policy evaluator.

    Production persistence can add richer ABAC expressions while preserving the
    decision port used by application services.
    """

    tenant_id: str
    actor_id: str
    resource_type: str
    resource_id: str
    action: str
    purposes: frozenset[str]
    region_from_subject: bool = False
    max_rows: int | None = None

