"""Iteration 2 tenant metadata and audit outbox.

Revision ID: 20260805_0001
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260805_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "user_accounts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("external_subject", sa.String(200), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("email_ciphertext", sa.Text()),
        sa.Column("department_id", sa.String(64)),
        sa.Column("attributes_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "external_subject", name="uq_user_subject"),
        sa.UniqueConstraint("tenant_id", "username", name="uq_user_username"),
    )
    op.create_index("ix_user_tenant_status", "user_accounts", ["tenant_id", "status"])
    op.create_index("ix_user_accounts_tenant_id", "user_accounts", ["tenant_id"])
    op.create_table(
        "agents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("owner_id", sa.String(64)),
        sa.Column("agent_type", sa.String(32), nullable=False),
        sa.Column("purpose", sa.String(100), nullable=False),
        sa.Column("risk_level", sa.String(24), nullable=False),
        sa.Column("service_principal_id", sa.String(200)),
        sa.Column("budget_policy", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_agent_code"),
    )
    op.create_index("ix_agent_tenant_status", "agents", ["tenant_id", "status"])
    op.create_index("ix_agents_tenant_id", "agents", ["tenant_id"])
    op.create_table(
        "policies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("policy_type", sa.String(32), nullable=False),
        sa.Column("document_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_policy_code"),
    )
    op.create_index("ix_policies_tenant_id", "policies", ["tenant_id"])
    op.create_table(
        "permission_grants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(200), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("purposes", sa.JSON(), nullable=False),
        sa.Column("region_from_subject", sa.Boolean(), nullable=False),
        sa.Column("max_rows", sa.Integer()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        *_timestamps(),
    )
    op.create_index("ix_grant_tenant_actor", "permission_grants", ["tenant_id", "actor_id"])
    op.create_index(
        "ix_grant_tenant_resource",
        "permission_grants",
        ["tenant_id", "resource_type", "resource_id"],
    )
    op.create_table(
        "data_apis",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("api_type", sa.String(32), nullable=False),
        sa.Column("semantic_version", sa.String(32), nullable=False),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("contract_json", sa.JSON(), nullable=False),
        sa.Column("lifecycle_status", sa.String(24), nullable=False),
        sa.Column("dataset_version", sa.Integer(), nullable=False),
        sa.Column("freshness_at", sa.String(40), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "tenant_id", "code", "semantic_version", name="uq_data_api_version"
        ),
    )
    op.create_index(
        "ix_data_api_tenant_lifecycle", "data_apis", ["tenant_id", "lifecycle_status"]
    )
    op.create_table(
        "audit_outbox",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(200), nullable=False),
        sa.Column("purpose", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("result_count", sa.Integer()),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_audit_outbox_delivery", "audit_outbox", ["status", "available_at"]
    )
    op.create_index(
        "ix_audit_outbox_tenant_trace", "audit_outbox", ["tenant_id", "trace_id"]
    )

    if op.get_bind().dialect.name == "postgresql":
        tenant_tables = (
            "user_accounts",
            "agents",
            "policies",
            "permission_grants",
            "data_apis",
            "audit_outbox",
        )
        op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation ON tenants USING "
            "(id = current_setting('app.current_tenant', true)) WITH CHECK "
            "(id = current_setting('app.current_tenant', true))"
        )
        for table in tenant_tables:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY tenant_isolation ON {table} USING "
                "(tenant_id = current_setting('app.current_tenant', true)) WITH CHECK "
                "(tenant_id = current_setting('app.current_tenant', true))"
            )


def downgrade() -> None:
    for table in (
        "audit_outbox",
        "data_apis",
        "permission_grants",
        "policies",
        "agents",
        "user_accounts",
        "tenants",
    ):
        op.drop_table(table)
