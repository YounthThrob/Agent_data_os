"""Tenant-safe SQLAlchemy repository implementations."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from agent_data_os.core.errors import AuditUnavailableError
from agent_data_os.domains.audit.models import AuditEvent
from agent_data_os.domains.data_service.models import QueryApiDefinition
from agent_data_os.domains.metadata.models import (
    AgentMetadata,
    DataApiMetadata,
    Tenant,
    UserAccount,
)
from agent_data_os.domains.policy.models import DecisionRequest, Grant
from agent_data_os.infrastructure.persistence.database import tenant_session
from agent_data_os.infrastructure.persistence.models import (
    AgentRow,
    AuditOutboxRow,
    DataApiRow,
    GrantRow,
    TenantRow,
    UserRow,
)


class SqlAlchemyMetadataRepository:
    """Metadata repository with mandatory tenant predicates on every aggregate."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def add_tenant(self, tenant: Tenant) -> None:
        # The tenant identifier itself is the boundary while provisioning a tenant.
        with tenant_session(self._sessions, tenant.id) as session:
            session.add(
                TenantRow(
                    id=tenant.id,
                    code=tenant.code,
                    name=tenant.name,
                    region=tenant.region,
                    status=tenant.status,
                    version=tenant.version,
                )
            )

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(TenantRow).where(TenantRow.id == tenant_id)
            )
            return None if row is None else self._to_tenant(row)

    def add_user(self, user: UserAccount) -> None:
        with tenant_session(self._sessions, user.tenant_id) as session:
            session.add(
                UserRow(
                    id=user.id,
                    tenant_id=user.tenant_id,
                    external_subject=user.external_subject,
                    username=user.username,
                    display_name=user.display_name,
                    department_id=user.department_id,
                    attributes_json=user.attributes,
                    status=user.status,
                    version=user.version,
                )
            )

    def get_user(self, tenant_id: str, user_id: str) -> UserAccount | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(UserRow).where(
                    UserRow.tenant_id == tenant_id, UserRow.id == user_id
                )
            )
            return None if row is None else self._to_user(row)

    def add_agent(self, agent: AgentMetadata) -> None:
        with tenant_session(self._sessions, agent.tenant_id) as session:
            session.add(
                AgentRow(
                    id=agent.id,
                    tenant_id=agent.tenant_id,
                    code=agent.code,
                    name=agent.name,
                    owner_id=agent.owner_id,
                    agent_type=agent.agent_type,
                    purpose=agent.purpose,
                    risk_level=agent.risk_level,
                    budget_policy=agent.budget_policy,
                    status=agent.status,
                    version=agent.version,
                )
            )

    def get_agent(self, tenant_id: str, agent_id: str) -> AgentMetadata | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(AgentRow).where(
                    AgentRow.tenant_id == tenant_id, AgentRow.id == agent_id
                )
            )
            return None if row is None else self._to_agent(row)

    def add_data_api(self, data_api: DataApiMetadata) -> None:
        with tenant_session(self._sessions, data_api.tenant_id) as session:
            session.add(
                DataApiRow(
                    id=data_api.id,
                    tenant_id=data_api.tenant_id,
                    code=data_api.code,
                    name=data_api.name,
                    api_type=data_api.api_type,
                    semantic_version=data_api.semantic_version,
                    dataset_id=data_api.dataset_id,
                    contract_json=data_api.contract,
                    lifecycle_status=data_api.lifecycle_status,
                    dataset_version=data_api.dataset_version,
                    freshness_at=data_api.freshness_at,
                    quality_score=data_api.quality_score,
                    version=data_api.version,
                )
            )

    def get_data_api(self, tenant_id: str, data_api_id: str) -> DataApiMetadata | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(DataApiRow).where(
                    DataApiRow.tenant_id == tenant_id, DataApiRow.id == data_api_id
                )
            )
            return None if row is None else self._to_data_api(row)

    @staticmethod
    def _to_tenant(row: TenantRow) -> Tenant:
        return Tenant(row.id, row.code, row.name, row.region, row.status, row.version)

    @staticmethod
    def _to_user(row: UserRow) -> UserAccount:
        return UserAccount(
            id=row.id,
            tenant_id=row.tenant_id,
            external_subject=row.external_subject,
            username=row.username,
            display_name=row.display_name,
            department_id=row.department_id,
            attributes=dict(row.attributes_json),
            status=row.status,
            version=row.version,
        )

    @staticmethod
    def _to_agent(row: AgentRow) -> AgentMetadata:
        return AgentMetadata(
            id=row.id,
            tenant_id=row.tenant_id,
            code=row.code,
            name=row.name,
            owner_id=row.owner_id,
            agent_type=row.agent_type,
            purpose=row.purpose,
            risk_level=row.risk_level,
            status=row.status,
            budget_policy=dict(row.budget_policy),
            version=row.version,
        )

    @staticmethod
    def _to_data_api(row: DataApiRow) -> DataApiMetadata:
        return DataApiMetadata(
            id=row.id,
            tenant_id=row.tenant_id,
            code=row.code,
            name=row.name,
            api_type=row.api_type,
            semantic_version=row.semantic_version,
            dataset_id=row.dataset_id,
            contract=dict(row.contract_json),
            lifecycle_status=row.lifecycle_status,
            dataset_version=row.dataset_version,
            freshness_at=row.freshness_at,
            quality_score=row.quality_score,
            version=row.version,
        )


class SqlAlchemyPolicyRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def find_grants(self, request: DecisionRequest) -> list[Grant]:
        now = datetime.now(timezone.utc)
        with tenant_session(self._sessions, request.subject.tenant_id) as session:
            rows = session.scalars(
                select(GrantRow).where(
                    GrantRow.tenant_id == request.subject.tenant_id,
                    GrantRow.actor_id == request.subject.actor_id,
                    GrantRow.resource_type == request.resource.resource_type,
                    GrantRow.resource_id == request.resource.resource_id,
                    GrantRow.action == request.action,
                    GrantRow.status == "ACTIVE",
                    or_(GrantRow.valid_from.is_(None), GrantRow.valid_from <= now),
                    or_(GrantRow.valid_to.is_(None), GrantRow.valid_to > now),
                )
            ).all()
            return [
                Grant(
                    tenant_id=row.tenant_id,
                    actor_id=row.actor_id,
                    resource_type=row.resource_type,
                    resource_id=row.resource_id,
                    action=row.action,
                    purposes=frozenset(row.purposes),
                    region_from_subject=row.region_from_subject,
                    max_rows=row.max_rows,
                )
                for row in rows
            ]


class SqlAlchemyQueryApiRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def get_published(self, tenant_id: str, api_code: str) -> QueryApiDefinition | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(DataApiRow).where(
                    DataApiRow.tenant_id == tenant_id,
                    DataApiRow.code == api_code,
                    DataApiRow.lifecycle_status == "PUBLISHED",
                ).order_by(DataApiRow.updated_at.desc()).limit(1)
            )
            if row is None:
                return None
            contract = row.contract_json
            return QueryApiDefinition(
                code=row.code,
                version=row.semantic_version,
                dataset_id=row.dataset_id,
                selectable_fields=frozenset(contract.get("selectable_fields", [])),
                allowed_filters={
                    key: frozenset(value)
                    for key, value in contract.get("allowed_filters", {}).items()
                },
                allowed_order_fields=frozenset(
                    contract.get("allowed_order_fields", [])
                ),
                allowed_purposes=frozenset(contract.get("allowed_purposes", [])),
                default_limit=int(contract.get("default_limit", 20)),
                maximum_limit=int(contract.get("maximum_limit", 100)),
                dataset_version=row.dataset_version,
                freshness_at=row.freshness_at,
                quality_score=row.quality_score,
                field_types=dict(contract.get("field_types", {})),
            )


class SqlAlchemyAuditRecorder:
    """Persist an immutable event to the transactional delivery outbox."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def record(self, event: AuditEvent) -> None:
        envelope = {
            "event_id": event.event_id,
            "tenant_id": event.tenant_id,
            "trace_id": event.trace_id,
            "actor_type": event.actor_type,
            "actor_id": event.actor_id,
            "action": event.action,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "purpose": event.purpose,
            "outcome": event.outcome,
            "error_code": event.error_code,
            "result_count": event.result_count,
            "payload": event.payload,
            "occurred_at": event.occurred_at.isoformat(),
        }
        canonical = json.dumps(
            envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        try:
            with tenant_session(self._sessions, event.tenant_id) as session:
                session.add(
                    AuditOutboxRow(
                        event_id=event.event_id,
                        tenant_id=event.tenant_id,
                        trace_id=event.trace_id,
                        actor_type=event.actor_type,
                        actor_id=event.actor_id,
                        action=event.action,
                        resource_type=event.resource_type,
                        resource_id=event.resource_id,
                        purpose=event.purpose,
                        outcome=event.outcome,
                        error_code=event.error_code,
                        result_count=event.result_count,
                        payload_json=envelope,
                        payload_hash=hashlib.sha256(canonical).hexdigest(),
                        available_at=event.occurred_at,
                        created_at=event.occurred_at,
                    )
                )
        except SQLAlchemyError as exc:
            raise AuditUnavailableError() from exc


def new_grant_row(*, tenant_id: str, grant: Grant) -> GrantRow:
    """Convenience factory for provisioning and integration tests."""

    return GrantRow(
        id=f"grant_{uuid.uuid4().hex}",
        tenant_id=tenant_id,
        actor_id=grant.actor_id,
        resource_type=grant.resource_type,
        resource_id=grant.resource_id,
        action=grant.action,
        purposes=sorted(grant.purposes),
        region_from_subject=grant.region_from_subject,
        max_rows=grant.max_rows,
    )
