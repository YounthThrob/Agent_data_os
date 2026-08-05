"""At-least-once relay for tenant-scoped audit and domain outboxes."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from agent_data_os.infrastructure.persistence.database import tenant_session
from agent_data_os.infrastructure.persistence.models import AuditOutboxRow, DomainOutboxRow


class EventPublisher(Protocol):
    def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None: ...


class SqlAlchemyOutboxRelay:
    """Relay one tenant at a time so RLS remains enforced for worker traffic."""

    def __init__(self, sessions: sessionmaker[Session], publisher: EventPublisher) -> None:
        self._sessions = sessions
        self._publisher = publisher

    def relay_audit(self, tenant_id: str, limit: int = 100) -> int:
        return self._relay(tenant_id, AuditOutboxRow, "audit.events.v1", limit)

    def relay_domain(self, tenant_id: str, limit: int = 100) -> int:
        return self._relay(tenant_id, DomainOutboxRow, None, limit)

    def _relay(self, tenant_id: str, model: type, topic: str | None, limit: int) -> int:
        delivered = 0
        now = datetime.now(timezone.utc)
        with tenant_session(self._sessions, tenant_id) as session:
            rows = session.scalars(
                select(model)
                .where(
                    model.tenant_id == tenant_id,
                    model.status == "PENDING",
                    model.available_at <= now,
                )
                .order_by(model.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            for row in rows:
                row.attempts += 1
                try:
                    event_topic = topic or row.topic
                    self._publisher.publish(event_topic, row.event_id, row.payload_json)
                except Exception as exc:
                    # Store only an exception-class fingerprint, never broker text
                    # that could echo credentials or event payloads.
                    row.last_error_code = hashlib.sha256(
                        type(exc).__name__.encode("utf-8")
                    ).hexdigest()[:16]
                    delay = min(300, 2 ** min(row.attempts, 8))
                    row.available_at = now + timedelta(seconds=delay)
                    continue
                row.status = "PUBLISHED"
                row.published_at = now
                row.last_error_code = None
                delivered += 1
        return delivered
