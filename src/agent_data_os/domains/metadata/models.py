"""Metadata aggregates persisted by the Iteration 2 repository adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Tenant:
    id: str
    code: str
    name: str
    region: str
    status: str = "ACTIVE"
    version: int = 1


@dataclass(frozen=True, slots=True)
class UserAccount:
    id: str
    tenant_id: str
    external_subject: str
    username: str
    display_name: str
    department_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ACTIVE"
    version: int = 1


@dataclass(frozen=True, slots=True)
class AgentMetadata:
    id: str
    tenant_id: str
    code: str
    name: str
    owner_id: str | None
    agent_type: str
    purpose: str
    risk_level: str
    status: str = "DRAFT"
    budget_policy: dict[str, Any] = field(default_factory=dict)
    version: int = 1


@dataclass(frozen=True, slots=True)
class DataApiMetadata:
    id: str
    tenant_id: str
    code: str
    name: str
    api_type: str
    semantic_version: str
    dataset_id: str
    contract: dict[str, Any]
    lifecycle_status: str = "DRAFT"
    dataset_version: int = 1
    freshness_at: str = ""
    quality_score: float = 0.0
    version: int = 1
