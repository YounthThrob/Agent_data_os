"""Stable ports for storage, processing, vectors and model access."""

from __future__ import annotations

from typing import Protocol

from agent_data_os.domains.knowledge.models import (
    Chunk,
    Document,
    DocumentVersion,
    IndexVersion,
    KnowledgeBase,
    SearchHit,
)


class KnowledgeRepository(Protocol):
    def save_knowledge_base(self, value: KnowledgeBase) -> None: ...
    def get_knowledge_base(self, tenant_id: str, kb_id: str) -> KnowledgeBase | None: ...
    def get_knowledge_base_by_code(
        self, tenant_id: str, code: str
    ) -> KnowledgeBase | None: ...
    def save_document(self, value: Document) -> None: ...
    def get_document(self, tenant_id: str, document_id: str) -> Document | None: ...
    def save_document_version(self, value: DocumentVersion) -> None: ...
    def get_document_version(
        self, tenant_id: str, version_id: str
    ) -> DocumentVersion | None: ...
    def save_chunks(self, values: tuple[Chunk, ...]) -> None: ...
    def list_chunks(
        self, tenant_id: str, knowledge_base_id: str
    ) -> tuple[Chunk, ...]: ...
    def get_authorized_chunks(
        self, tenant_id: str, chunk_ids: tuple[str, ...], acl_tokens: frozenset[str]
    ) -> tuple[Chunk, ...]: ...
    def save_index_version(self, value: IndexVersion) -> None: ...
    def next_index_version_number(
        self, tenant_id: str, knowledge_base_id: str
    ) -> int: ...
    def get_index_version(
        self, tenant_id: str, index_id: str
    ) -> IndexVersion | None: ...
    def publish_index(self, knowledge_base: KnowledgeBase, index: IndexVersion) -> None: ...


class ObjectStoragePort(Protocol):
    def create_upload(self, object_ref: str, size_bytes: int, mime_type: str) -> str: ...
    def read(self, object_ref: str) -> bytes: ...


class FileSecurityScanner(Protocol):
    def scan(self, object_ref: str, content: bytes) -> None: ...


class DocumentParser(Protocol):
    def parse(self, content: bytes, mime_type: str) -> tuple[dict[str, object], ...]: ...


class EmbeddingPort(Protocol):
    model_version: str
    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class VectorIndexPort(Protocol):
    def upsert(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        index_version_id: str,
        chunks: tuple[Chunk, ...],
        vectors: tuple[tuple[float, ...], ...],
    ) -> None: ...
    def search(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        index_version_id: str,
        vector: tuple[float, ...],
        acl_tokens: frozenset[str],
        limit: int,
    ) -> tuple[SearchHit, ...]: ...


class GenerationPort(Protocol):
    deployment_id: str
    def generate(self, query: str, evidence: tuple[Chunk, ...]) -> str: ...
