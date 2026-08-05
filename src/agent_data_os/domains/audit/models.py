"""Immutable audit event values.

Audit payloads intentionally carry identifiers, counts, versions and hashes only.
Query values and returned business data must never be placed in the outbox.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    tenant_id: str
    trace_id: str
    actor_type: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    purpose: str
    outcome: str
    error_code: str | None = None
    result_count: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        trace_id: str,
        actor_type: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        purpose: str,
        outcome: str,
        error_code: str | None = None,
        result_count: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "AuditEvent":
        """Create a globally unique, timestamped audit event."""

        return cls(
            event_id=f"audit_{uuid.uuid4().hex}",
            tenant_id=tenant_id,
            trace_id=trace_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            purpose=purpose,
            outcome=outcome,
            error_code=error_code,
            result_count=result_count,
            payload=payload or {},
        )
