"""Knowledge base, document, chunk and blue/green index values."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from agent_data_os.core.errors import InvalidStateTransitionError


class KnowledgeBaseStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class DocumentStatus(str, Enum):
    UPLOADING = "UPLOADING"
    READY = "READY"
    PROCESSING = "PROCESSING"
    INDEXED = "INDEXED"
    QUARANTINED = "QUARANTINED"
    REVOKED = "REVOKED"


class IndexStatus(str, Enum):
    BUILDING = "BUILDING"
    READY = "READY"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class KnowledgeBase:
    id: str
    tenant_id: str
    code: str
    name: str
    owner_id: str
    allowed_purposes: frozenset[str]
    max_top_k: int = 8
    allow_generation: bool = True
    status: KnowledgeBaseStatus = KnowledgeBaseStatus.ACTIVE
    active_index_version_id: str | None = None
    version: int = 1

    def publish_index(self, index_id: str) -> "KnowledgeBase":
        if self.status is not KnowledgeBaseStatus.ACTIVE:
            raise InvalidStateTransitionError("knowledge base is not active")
        return replace(
            self, active_index_version_id=index_id, version=self.version + 1
        )


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    tenant_id: str
    knowledge_base_id: str
    title: str
    classification: str
    owner_id: str
    acl_tokens: frozenset[str]
    status: DocumentStatus = DocumentStatus.UPLOADING
    version: int = 1


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    id: str
    tenant_id: str
    document_id: str
    version_number: int
    object_ref: str
    file_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    parser_version: str
    chunk_strategy_version: str
    status: DocumentStatus = DocumentStatus.READY
    index_version_id: str | None = None


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    tenant_id: str
    knowledge_base_id: str
    document_id: str
    document_version_id: str
    ordinal: int
    content: str
    content_hash: str
    acl_tokens: frozenset[str]
    classification: str
    page_number: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IndexVersion:
    id: str
    tenant_id: str
    knowledge_base_id: str
    version_number: int
    embedding_model_version: str
    parser_version: str
    chunk_strategy_version: str
    status: IndexStatus
    chunk_count: int = 0


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk_id: str
    score: float


@dataclass(frozen=True, slots=True)
class Evidence:
    chunk_id: str
    document_id: str
    document_version_id: str
    title: str
    excerpt: str
    score: float
    page_number: int | None
    classification: str


@dataclass(frozen=True, slots=True)
class KnowledgeResult:
    answer: str | None
    sufficient_evidence: bool
    evidence: tuple[Evidence, ...]
    knowledge_base_id: str
    index_version_id: str
    candidate_count: int
    authorized_count: int
    generated: bool
