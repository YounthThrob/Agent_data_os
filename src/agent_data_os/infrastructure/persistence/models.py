"""Relational metadata and audit-outbox schema."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class TenantRow(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserRow(Base):
    __tablename__ = "user_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_subject", name="uq_user_subject"),
        UniqueConstraint("tenant_id", "username", name="uq_user_username"),
        Index("ix_user_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_subject: Mapped[str] = mapped_column(String(200), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email_ciphertext: Mapped[str | None] = mapped_column(Text)
    department_id: Mapped[str | None] = mapped_column(String(64))
    attributes_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, default=dict, nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentRow(Base):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_agent_code"),
        Index("ix_agent_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(64))
    agent_type: Mapped[str] = mapped_column(String(32), nullable=False)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(24), nullable=False)
    service_principal_id: Mapped[str | None] = mapped_column(String(200))
    budget_policy: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, default=dict, nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PolicyRow(Base):
    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_policy_code"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    policy_type: Mapped[str] = mapped_column(String(32), nullable=False)
    document_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GrantRow(Base):
    __tablename__ = "permission_grants"
    __table_args__ = (
        Index("ix_grant_tenant_actor", "tenant_id", "actor_id"),
        Index("ix_grant_tenant_resource", "tenant_id", "resource_type", "resource_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    purposes: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list, nullable=False)
    region_from_subject: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_rows: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DataApiRow(Base):
    __tablename__ = "data_apis"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "code", "semantic_version", name="uq_data_api_version"
        ),
        Index("ix_data_api_tenant_lifecycle", "tenant_id", "lifecycle_status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    api_type: Mapped[str] = mapped_column(String(32), nullable=False)
    semantic_version: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(24), nullable=False)
    dataset_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    freshness_at: Mapped[str] = mapped_column(String(40), nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditOutboxRow(Base):
    __tablename__ = "audit_outbox"
    __table_args__ = (
        Index("ix_audit_outbox_delivery", "status", "available_at"),
        Index("ix_audit_outbox_tenant_trace", "tenant_id", "trace_id"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    result_count: Mapped[int | None] = mapped_column(Integer)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="PENDING", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
