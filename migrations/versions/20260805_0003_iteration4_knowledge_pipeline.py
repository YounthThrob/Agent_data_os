"""Iteration 4 knowledge processing and retrieval metadata.

Revision ID: 20260805_0003
Revises: 20260805_0002
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260805_0003"
down_revision: str | None = "20260805_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("allowed_purposes", sa.JSON(), nullable=False),
        sa.Column("max_top_k", sa.Integer(), nullable=False),
        sa.Column("allow_generation", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("active_index_version_id", sa.String(64)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_knowledge_base_code"),
    )
    op.create_index(
        "ix_knowledge_base_tenant_status", "knowledge_bases", ["tenant_id", "status"]
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("knowledge_base_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("classification", sa.String(24), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("acl_tokens", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_document_tenant_kb", "documents", ["tenant_id", "knowledge_base_id"]
    )
    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("object_ref", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(300), nullable=False),
        sa.Column("mime_type", sa.String(160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("chunk_strategy_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("index_version_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "document_id", "version_number", name="uq_document_version"
        ),
    )
    op.create_index(
        "ix_document_version_tenant_document",
        "document_versions",
        ["tenant_id", "document_id"],
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("knowledge_base_id", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("document_version_id", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content_ciphertext", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("acl_tokens", sa.JSON(), nullable=False),
        sa.Column("classification", sa.String(24), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("start_offset", sa.Integer()),
        sa.Column("end_offset", sa.Integer()),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "document_version_id", "ordinal", name="uq_chunk_ordinal"
        ),
    )
    op.create_index(
        "ix_chunk_tenant_kb", "knowledge_chunks", ["tenant_id", "knowledge_base_id"]
    )
    op.create_table(
        "knowledge_index_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("knowledge_base_id", sa.String(64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("embedding_model_version", sa.String(100), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("chunk_strategy_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "tenant_id",
            "knowledge_base_id",
            "version_number",
            name="uq_kb_index_version",
        ),
    )
    op.create_index(
        "ix_kb_index_tenant_status",
        "knowledge_index_versions",
        ["tenant_id", "status"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "knowledge_bases",
            "documents",
            "document_versions",
            "knowledge_chunks",
            "knowledge_index_versions",
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
        "knowledge_index_versions",
        "knowledge_chunks",
        "document_versions",
        "documents",
        "knowledge_bases",
    ):
        op.drop_table(table)
