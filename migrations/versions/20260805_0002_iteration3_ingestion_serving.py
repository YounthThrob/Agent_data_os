"""Iteration 3 ingestion, catalog, serving and domain outbox.

Revision ID: 20260805_0002
Revises: 20260805_0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260805_0002"
down_revision: str | None = "20260805_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("audit_outbox", sa.Column("last_error_code", sa.String(64)))
    op.create_table(
        "data_sources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("connector_version", sa.String(64), nullable=False),
        sa.Column("connection_json", sa.JSON(), nullable=False),
        sa.Column("secret_ref", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("discovered_schema_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "name", name="uq_data_source_name"),
    )
    op.create_index(
        "ix_data_source_tenant_status", "data_sources", ["tenant_id", "status"]
    )
    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("data_source_id", sa.String(64), nullable=False),
        sa.Column("source_objects_json", sa.JSON(), nullable=False),
        sa.Column("sync_mode", sa.String(32), nullable=False),
        sa.Column("target_dataset_name", sa.String(200), nullable=False),
        sa.Column("schedule_json", sa.JSON(), nullable=False),
        sa.Column("incremental_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "name", name="uq_sync_job_name"),
    )
    op.create_index(
        "ix_sync_job_tenant_status", "sync_jobs", ["tenant_id", "status"]
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("sync_job_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("checkpoint_json", sa.JSON(), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("result_hash", sa.String(64)),
        sa.Column("dataset_version_id", sa.String(64)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint(
            "tenant_id", "sync_job_id", "idempotency_key", name="uq_run_idempotency"
        ),
    )
    op.create_index(
        "ix_ingestion_run_tenant_status", "ingestion_runs", ["tenant_id", "status"]
    )
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("logical_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("active_version_id", sa.String(64)),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "logical_name", name="uq_dataset_logical_name"),
    )
    op.create_index("ix_dataset_tenant_status", "datasets", ["tenant_id", "status"])
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("checkpoint_json", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "dataset_id", "version_number", name="uq_dataset_version"
        ),
    )
    op.create_index(
        "ix_dataset_version_tenant_status",
        "dataset_versions",
        ["tenant_id", "status"],
    )
    op.create_table(
        "serving_rows",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("dataset_version_id", sa.String(64), nullable=False),
        sa.Column("row_key", sa.String(128), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "dataset_version_id", "row_key", name="uq_serving_row_key"
        ),
    )
    op.create_index(
        "ix_serving_tenant_dataset", "serving_rows", ["tenant_id", "dataset_id"]
    )
    op.create_table(
        "domain_outbox",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(64)),
    )
    op.create_index(
        "ix_domain_outbox_delivery", "domain_outbox", ["status", "available_at"]
    )
    op.create_index(
        "ix_domain_outbox_tenant_aggregate",
        "domain_outbox",
        ["tenant_id", "aggregate_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "data_sources",
            "sync_jobs",
            "ingestion_runs",
            "datasets",
            "dataset_versions",
            "serving_rows",
            "domain_outbox",
        ):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY tenant_isolation ON {table} USING "
                "(tenant_id = current_setting('app.current_tenant', true)) WITH CHECK "
                "(tenant_id = current_setting('app.current_tenant', true))"
            )


def downgrade() -> None:
    for table in (
        "domain_outbox",
        "serving_rows",
        "dataset_versions",
        "datasets",
        "ingestion_runs",
        "sync_jobs",
        "data_sources",
    ):
        op.drop_table(table)
    op.drop_column("audit_outbox", "last_error_code")
