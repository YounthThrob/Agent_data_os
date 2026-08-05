"""Encrypted tenant-scoped SQLAlchemy knowledge repository."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from agent_data_os.core.errors import InvalidStateTransitionError
from agent_data_os.domains.knowledge.models import (
    Chunk,
    Document,
    DocumentStatus,
    DocumentVersion,
    IndexStatus,
    IndexVersion,
    KnowledgeBase,
    KnowledgeBaseStatus,
)
from agent_data_os.infrastructure.persistence.database import tenant_session
from agent_data_os.infrastructure.persistence.models import (
    DocumentRow,
    DocumentVersionRow,
    KnowledgeBaseRow,
    KnowledgeChunkRow,
    KnowledgeIndexVersionRow,
    utc_now,
)


class ContentCipher(Protocol):
    def encrypt(self, tenant_id: str, plaintext: str) -> str: ...
    def decrypt(self, tenant_id: str, ciphertext: str) -> str: ...


class RejectingContentCipher:
    def encrypt(self, tenant_id: str, plaintext: str) -> str:
        raise InvalidStateTransitionError("knowledge content cipher is not configured")

    def decrypt(self, tenant_id: str, ciphertext: str) -> str:
        raise InvalidStateTransitionError("knowledge content cipher is not configured")


class DevelopmentContentCipher:
    """Encoding-only test adapter; forbidden for production composition."""

    def encrypt(self, tenant_id: str, plaintext: str) -> str:
        return base64.b64encode(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, tenant_id: str, ciphertext: str) -> str:
        return base64.b64decode(ciphertext.encode("ascii")).decode("utf-8")


class SqlAlchemyKnowledgeRepository:
    def __init__(self, sessions: sessionmaker[Session], cipher: ContentCipher) -> None:
        self._sessions = sessions
        self._cipher = cipher

    def save_knowledge_base(self, value: KnowledgeBase) -> None:
        with tenant_session(self._sessions, value.tenant_id) as session:
            row = session.scalar(
                select(KnowledgeBaseRow).where(
                    KnowledgeBaseRow.tenant_id == value.tenant_id,
                    KnowledgeBaseRow.id == value.id,
                )
            )
            if row is None:
                row = KnowledgeBaseRow(id=value.id, tenant_id=value.tenant_id)
                session.add(row)
            self._apply_kb(row, value)

    def get_knowledge_base(self, tenant_id: str, kb_id: str) -> KnowledgeBase | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(KnowledgeBaseRow).where(
                    KnowledgeBaseRow.tenant_id == tenant_id,
                    KnowledgeBaseRow.id == kb_id,
                )
            )
            return None if row is None else self._to_kb(row)

    def get_knowledge_base_by_code(
        self, tenant_id: str, code: str
    ) -> KnowledgeBase | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(KnowledgeBaseRow).where(
                    KnowledgeBaseRow.tenant_id == tenant_id,
                    KnowledgeBaseRow.code == code,
                    KnowledgeBaseRow.status == KnowledgeBaseStatus.ACTIVE.value,
                )
            )
            return None if row is None else self._to_kb(row)

    def save_document(self, value: Document) -> None:
        with tenant_session(self._sessions, value.tenant_id) as session:
            row = session.scalar(
                select(DocumentRow).where(
                    DocumentRow.tenant_id == value.tenant_id,
                    DocumentRow.id == value.id,
                )
            )
            if row is None:
                row = DocumentRow(id=value.id, tenant_id=value.tenant_id)
                session.add(row)
            row.knowledge_base_id = value.knowledge_base_id
            row.title = value.title
            row.classification = value.classification
            row.owner_id = value.owner_id
            row.acl_tokens = sorted(value.acl_tokens)
            row.status = value.status.value
            row.version = value.version
            row.updated_at = utc_now()

    def get_document(self, tenant_id: str, document_id: str) -> Document | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(DocumentRow).where(
                    DocumentRow.tenant_id == tenant_id, DocumentRow.id == document_id
                )
            )
            return None if row is None else self._to_document(row)

    def save_document_version(self, value: DocumentVersion) -> None:
        with tenant_session(self._sessions, value.tenant_id) as session:
            row = session.scalar(
                select(DocumentVersionRow).where(
                    DocumentVersionRow.tenant_id == value.tenant_id,
                    DocumentVersionRow.id == value.id,
                )
            )
            if row is None:
                row = DocumentVersionRow(
                    id=value.id,
                    tenant_id=value.tenant_id,
                )
                session.add(row)
            row.document_id = value.document_id
            row.version_number = value.version_number
            row.object_ref = value.object_ref
            row.file_name = value.file_name
            row.mime_type = value.mime_type
            row.size_bytes = value.size_bytes
            row.sha256 = value.sha256
            row.parser_version = value.parser_version
            row.chunk_strategy_version = value.chunk_strategy_version
            row.status = value.status.value
            row.index_version_id = value.index_version_id

    def get_document_version(
        self, tenant_id: str, version_id: str
    ) -> DocumentVersion | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(DocumentVersionRow).where(
                    DocumentVersionRow.tenant_id == tenant_id,
                    DocumentVersionRow.id == version_id,
                )
            )
            return None if row is None else self._to_document_version(row)

    def save_chunks(self, values: tuple[Chunk, ...]) -> None:
        if not values:
            return
        tenant_id = values[0].tenant_id
        if any(value.tenant_id != tenant_id for value in values):
            raise InvalidStateTransitionError("cross-tenant chunk batch is forbidden")
        with tenant_session(self._sessions, tenant_id) as session:
            for value in values:
                row = session.scalar(
                    select(KnowledgeChunkRow).where(
                        KnowledgeChunkRow.tenant_id == value.tenant_id,
                        KnowledgeChunkRow.id == value.id,
                    )
                )
                if row is None:
                    row = KnowledgeChunkRow(
                        id=value.id,
                        tenant_id=value.tenant_id,
                    )
                    session.add(row)
                row.knowledge_base_id = value.knowledge_base_id
                row.document_id = value.document_id
                row.document_version_id = value.document_version_id
                row.ordinal = value.ordinal
                row.content_ciphertext = self._cipher.encrypt(
                    value.tenant_id, value.content
                )
                row.content_hash = value.content_hash
                row.acl_tokens = sorted(value.acl_tokens)
                row.classification = value.classification
                row.page_number = value.page_number
                row.start_offset = value.start_offset
                row.end_offset = value.end_offset
                row.metadata_json = value.metadata

    def list_chunks(
        self, tenant_id: str, knowledge_base_id: str
    ) -> tuple[Chunk, ...]:
        with tenant_session(self._sessions, tenant_id) as session:
            rows = session.scalars(
                select(KnowledgeChunkRow).where(
                    KnowledgeChunkRow.tenant_id == tenant_id,
                    KnowledgeChunkRow.knowledge_base_id == knowledge_base_id,
                )
            ).all()
            return tuple(self._to_chunk(row) for row in rows)

    def get_authorized_chunks(
        self, tenant_id: str, chunk_ids: tuple[str, ...], acl_tokens: frozenset[str]
    ) -> tuple[Chunk, ...]:
        if not chunk_ids:
            return ()
        with tenant_session(self._sessions, tenant_id) as session:
            rows = session.execute(
                select(KnowledgeChunkRow, DocumentRow)
                .join(
                    DocumentRow,
                    (DocumentRow.tenant_id == KnowledgeChunkRow.tenant_id)
                    & (DocumentRow.id == KnowledgeChunkRow.document_id),
                )
                .where(
                    KnowledgeChunkRow.tenant_id == tenant_id,
                    KnowledgeChunkRow.id.in_(chunk_ids),
                    DocumentRow.status == DocumentStatus.INDEXED.value,
                )
            ).all()
            by_id = {
                chunk.id: self._to_chunk(chunk)
                for chunk, _ in rows
                if set(chunk.acl_tokens).intersection(acl_tokens)
            }
            return tuple(by_id[value] for value in chunk_ids if value in by_id)

    def save_index_version(self, value: IndexVersion) -> None:
        with tenant_session(self._sessions, value.tenant_id) as session:
            row = session.scalar(
                select(KnowledgeIndexVersionRow).where(
                    KnowledgeIndexVersionRow.tenant_id == value.tenant_id,
                    KnowledgeIndexVersionRow.id == value.id,
                )
            )
            if row is None:
                row = KnowledgeIndexVersionRow(id=value.id, tenant_id=value.tenant_id)
                session.add(row)
            self._apply_index(row, value)

    def next_index_version_number(
        self, tenant_id: str, knowledge_base_id: str
    ) -> int:
        with tenant_session(self._sessions, tenant_id) as session:
            current = session.scalar(
                select(func.max(KnowledgeIndexVersionRow.version_number)).where(
                    KnowledgeIndexVersionRow.tenant_id == tenant_id,
                    KnowledgeIndexVersionRow.knowledge_base_id == knowledge_base_id,
                )
            )
            return (current or 0) + 1

    def get_index_version(
        self, tenant_id: str, index_id: str
    ) -> IndexVersion | None:
        with tenant_session(self._sessions, tenant_id) as session:
            row = session.scalar(
                select(KnowledgeIndexVersionRow).where(
                    KnowledgeIndexVersionRow.tenant_id == tenant_id,
                    KnowledgeIndexVersionRow.id == index_id,
                )
            )
            return None if row is None else self._to_index(row)

    def publish_index(self, knowledge_base: KnowledgeBase, index: IndexVersion) -> None:
        with tenant_session(self._sessions, knowledge_base.tenant_id) as session:
            kb_row = session.scalar(
                select(KnowledgeBaseRow)
                .where(
                    KnowledgeBaseRow.tenant_id == knowledge_base.tenant_id,
                    KnowledgeBaseRow.id == knowledge_base.id,
                )
                .with_for_update()
            )
            index_row = session.scalar(
                select(KnowledgeIndexVersionRow)
                .where(
                    KnowledgeIndexVersionRow.tenant_id == knowledge_base.tenant_id,
                    KnowledgeIndexVersionRow.id == index.id,
                )
                .with_for_update()
            )
            if kb_row is None or index_row is None or index_row.status != "READY":
                raise InvalidStateTransitionError("index cannot be published")
            old_rows = session.scalars(
                select(KnowledgeIndexVersionRow).where(
                    KnowledgeIndexVersionRow.tenant_id == knowledge_base.tenant_id,
                    KnowledgeIndexVersionRow.knowledge_base_id == knowledge_base.id,
                    KnowledgeIndexVersionRow.status == "PUBLISHED",
                )
            ).all()
            for old in old_rows:
                old.status = "RETIRED"
            self._apply_index(index_row, index)
            index_row.published_at = datetime.now(timezone.utc)
            self._apply_kb(kb_row, knowledge_base)

    @staticmethod
    def _apply_kb(row: KnowledgeBaseRow, value: KnowledgeBase) -> None:
        row.code = value.code
        row.name = value.name
        row.owner_id = value.owner_id
        row.allowed_purposes = sorted(value.allowed_purposes)
        row.max_top_k = value.max_top_k
        row.allow_generation = value.allow_generation
        row.status = value.status.value
        row.active_index_version_id = value.active_index_version_id
        row.version = value.version
        row.updated_at = utc_now()

    @staticmethod
    def _apply_index(row: KnowledgeIndexVersionRow, value: IndexVersion) -> None:
        row.knowledge_base_id = value.knowledge_base_id
        row.version_number = value.version_number
        row.embedding_model_version = value.embedding_model_version
        row.parser_version = value.parser_version
        row.chunk_strategy_version = value.chunk_strategy_version
        row.status = value.status.value
        row.chunk_count = value.chunk_count

    @staticmethod
    def _to_kb(row: KnowledgeBaseRow) -> KnowledgeBase:
        return KnowledgeBase(
            id=row.id,
            tenant_id=row.tenant_id,
            code=row.code,
            name=row.name,
            owner_id=row.owner_id,
            allowed_purposes=frozenset(row.allowed_purposes),
            max_top_k=row.max_top_k,
            allow_generation=row.allow_generation,
            status=KnowledgeBaseStatus(row.status),
            active_index_version_id=row.active_index_version_id,
            version=row.version,
        )

    @staticmethod
    def _to_document(row: DocumentRow) -> Document:
        return Document(
            id=row.id,
            tenant_id=row.tenant_id,
            knowledge_base_id=row.knowledge_base_id,
            title=row.title,
            classification=row.classification,
            owner_id=row.owner_id,
            acl_tokens=frozenset(row.acl_tokens),
            status=DocumentStatus(row.status),
            version=row.version,
        )

    @staticmethod
    def _to_document_version(row: DocumentVersionRow) -> DocumentVersion:
        return DocumentVersion(
            id=row.id,
            tenant_id=row.tenant_id,
            document_id=row.document_id,
            version_number=row.version_number,
            object_ref=row.object_ref,
            file_name=row.file_name,
            mime_type=row.mime_type,
            size_bytes=row.size_bytes,
            sha256=row.sha256,
            parser_version=row.parser_version,
            chunk_strategy_version=row.chunk_strategy_version,
            status=DocumentStatus(row.status),
            index_version_id=row.index_version_id,
        )

    def _to_chunk(self, row: KnowledgeChunkRow) -> Chunk:
        return Chunk(
            id=row.id,
            tenant_id=row.tenant_id,
            knowledge_base_id=row.knowledge_base_id,
            document_id=row.document_id,
            document_version_id=row.document_version_id,
            ordinal=row.ordinal,
            content=self._cipher.decrypt(row.tenant_id, row.content_ciphertext),
            content_hash=row.content_hash,
            acl_tokens=frozenset(row.acl_tokens),
            classification=row.classification,
            page_number=row.page_number,
            start_offset=row.start_offset,
            end_offset=row.end_offset,
            metadata=dict(row.metadata_json),
        )

    @staticmethod
    def _to_index(row: KnowledgeIndexVersionRow) -> IndexVersion:
        return IndexVersion(
            id=row.id,
            tenant_id=row.tenant_id,
            knowledge_base_id=row.knowledge_base_id,
            version_number=row.version_number,
            embedding_model_version=row.embedding_model_version,
            parser_version=row.parser_version,
            chunk_strategy_version=row.chunk_strategy_version,
            status=IndexStatus(row.status),
            chunk_count=row.chunk_count,
        )
