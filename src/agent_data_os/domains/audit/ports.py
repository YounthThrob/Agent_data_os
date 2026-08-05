"""Ports owned by the audit domain."""

from __future__ import annotations

from typing import Protocol

from agent_data_os.domains.audit.models import AuditEvent


class AuditRecorder(Protocol):
    """Persist an audit event durably before protected data is returned."""

    def record(self, event: AuditEvent) -> None:
        ...
