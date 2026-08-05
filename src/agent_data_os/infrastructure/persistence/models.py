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
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class DataSourceRow(Base):
    __tablename__ = "data_sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_data_source_name"),
        Index("ix_data_source_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    connector_version: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    secret_ref: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    discovered_schema_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_DOCUMENT, default=list, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SyncJobRow(Base):
    __tablename__ = "sync_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_sync_job_name"),
        Index("ix_sync_job_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    data_source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_objects_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_DOCUMENT, nullable=False
    )
    sync_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    target_dataset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    schedule_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    incremental_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IngestionRunRow(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "sync_job_id", "idempotency_key", name="uq_run_idempotency"
        ),
        Index("ix_ingestion_run_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sync_job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    checkpoint_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    dataset_version_id: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DatasetRow(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "logical_name", name="uq_dataset_logical_name"),
        Index("ix_dataset_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    active_version_id: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DatasetVersionRow(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "dataset_id", "version_number", name="uq_dataset_version"
        ),
        Index("ix_dataset_version_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON_DOCUMENT, nullable=False)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    checkpoint_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ServingRow(Base):
    __tablename__ = "serving_rows"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "dataset_version_id", "row_key", name="uq_serving_row_key"
        ),
        Index("ix_serving_tenant_dataset", "tenant_id", "dataset_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    row_key: Mapped[str] = mapped_column(String(128), nullable=False)
    data_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DomainOutboxRow(Base):
    __tablename__ = "domain_outbox"
    __table_args__ = (
        Index("ix_domain_outbox_delivery", "status", "available_at"),
        Index("ix_domain_outbox_tenant_aggregate", "tenant_id", "aggregate_id"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="PENDING", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class KnowledgeBaseRow(Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_knowledge_base_code"),
        Index("ix_knowledge_base_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed_purposes: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    max_top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    allow_generation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    active_index_version_id: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DocumentRow(Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_document_tenant_kb", "tenant_id", "knowledge_base_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    classification: Mapped[str] = mapped_column(String(24), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    acl_tokens: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DocumentVersionRow(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "document_id", "version_number", name="uq_document_version"
        ),
        Index("ix_document_version_tenant_document", "tenant_id", "document_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    object_ref: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_strategy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    index_version_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeChunkRow(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "document_version_id", "ordinal", name="uq_chunk_ordinal"
        ),
        Index("ix_chunk_tenant_kb", "tenant_id", "knowledge_base_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    acl_tokens: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    classification: Mapped[str] = mapped_column(String(24), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeIndexVersionRow(Base):
    __tablename__ = "knowledge_index_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "knowledge_base_id", "version_number", name="uq_kb_index_version"
        ),
        Index("ix_kb_index_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_strategy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
