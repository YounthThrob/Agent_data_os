"""Request and security context shared across the use-case boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActorType(str, Enum):
    USER = "USER"
    AGENT = "AGENT"
    SERVICE = "SERVICE"


@dataclass(frozen=True, slots=True)
class SecurityContext:
    """Verified identity data; never construct it from untrusted request fields."""

    tenant_id: str
    actor_type: ActorType
    actor_id: str
    purpose: str
    delegated_user_id: str | None = None
    agent_version: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    scopes: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str
    trace_id: str
    security: SecurityContext
    environment: str

