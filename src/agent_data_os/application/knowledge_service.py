"""Knowledge ingestion and retrieval orchestration with deterministic security gates."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import replace
from typing import Any

from agent_data_os.core.context import RequestContext
from agent_data_os.core.errors import (
    AppError,
    ConflictError,
    FileSecurityBlockedError,
    IndexVersionUnavailableError,
    InsufficientEvidenceError,
    InvalidArgumentError,
    PolicyDeniedError,
    PromptInjectionBlockedError,
    ResourceNotVisibleError,
)
from agent_data_os.domains.audit.models import AuditEvent
from agent_data_os.domains.audit.ports import AuditRecorder
from agent_data_os.domains.knowledge.models import (
    Chunk,
    Document,
    DocumentStatus,
    DocumentVersion,
    Evidence,
    IndexStatus,
    IndexVersion,
    KnowledgeBase,
    KnowledgeResult,
)
from agent_data_os.domains.knowledge.ports import (
    DocumentParser,
    EmbeddingPort,
    FileSecurityScanner,
    GenerationPort,
    KnowledgeRepository,
    ObjectStoragePort,
    VectorIndexPort,
)


ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/png",
        "image/jpeg",
        "text/plain",
    }
)
ALLOWED_CLASSIFICATIONS = frozenset({"PUBLIC", "INTERNAL", "CONFIDENTIAL", "SECRET"})


class PromptInjectionGuard:
    """Deterministic first-line guard; production may add a classifier behind it."""

    _patterns = tuple(
        re.compile(pattern, re.IGNORECASE)
        for pattern in (
            r"ignore\s+(all\s+)?previous\s+instructions",
            r"reveal\s+(the\s+)?system\s+prompt",
            r"developer\s+message",
            r"execute\s+(this\s+)?tool",
            r"绕过.{0,8}(指令|权限|系统)",
            r"忽略.{0,8}(之前|以上).{0,8}指令",
        )
    )

    def is_suspicious(self, value: str) -> bool:
        return any(pattern.search(value) for pattern in self._patterns)

    def validate_query(self, value: str) -> None:
        if self.is_suspicious(value):
            raise PromptInjectionBlockedError()


class KnowledgeApplicationService:
    def __init__(
        self,
        repository: KnowledgeRepository,
        object_storage: ObjectStoragePort,
        scanner: FileSecurityScanner,
        parser: DocumentParser,
        embedding: EmbeddingPort,
        vector_index: VectorIndexPort,
        generation: GenerationPort,
        audit: AuditRecorder,
        guard: PromptInjectionGuard | None = None,
    ) -> None:
        self._repository = repository
        self._storage = object_storage
        self._scanner = scanner
        self._parser = parser
        self._embedding = embedding
        self._vector_index = vector_index
        self._generation = generation
        self._audit = audit
        self._guard = guard or PromptInjectionGuard()

    def create_knowledge_base(
        self,
        context: RequestContext,
        *,
        code: str,
        name: str,
        owner_id: str,
        allowed_purposes: frozenset[str],
        max_top_k: int,
        allow_generation: bool,
    ) -> KnowledgeBase:
        if not allowed_purposes:
            raise InvalidArgumentError("knowledge base requires an allowed purpose")
        if not 1 <= max_top_k <= 50:
            raise InvalidArgumentError("max_top_k must be between 1 and 50")
        if self._repository.get_knowledge_base_by_code(
            context.security.tenant_id, code
        ) is not None:
            raise ConflictError("knowledge base code already exists")
        value = KnowledgeBase(
            id=f"kb_{uuid.uuid4().hex}",
            tenant_id=context.security.tenant_id,
            code=code,
            name=name,
            owner_id=owner_id,
            allowed_purposes=allowed_purposes,
            max_top_k=max_top_k,
            allow_generation=allow_generation,
        )
        self._repository.save_knowledge_base(value)
        return value

    def create_upload(
        self,
        context: RequestContext,
        *,
        knowledge_base_id: str,
        file_name: str,
        size_bytes: int,
        mime_type: str,
        sha256: str,
        classification: str,
        acl_tokens: frozenset[str],
    ) -> tuple[Document, DocumentVersion, str]:
        kb = self._require_kb(context, knowledge_base_id)
        if mime_type not in ALLOWED_MIME_TYPES:
            raise InvalidArgumentError("unsupported document MIME type")
        if not 1 <= size_bytes <= 100 * 1024 * 1024:
            raise InvalidArgumentError("file size is outside the allowed range")
        if not re.fullmatch(r"[a-f0-9]{64}", sha256):
            raise InvalidArgumentError("sha256 must be a lowercase hexadecimal digest")
        classification = classification.upper()
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise InvalidArgumentError("unsupported data classification")
        allowed_acl_namespaces = {"tenant", "user", "department", "group", "role"}
        if not acl_tokens or any(
            ":" not in token
            or token.split(":", 1)[0] not in allowed_acl_namespaces
            or len(token) > 200
            or (token.startswith("tenant:") and token != "tenant:all")
            for token in acl_tokens
        ):
            raise InvalidArgumentError("at least one namespaced ACL token is required")
        document_id = f"document_{uuid.uuid4().hex}"
        version_id = f"document_version_{uuid.uuid4().hex}"
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", file_name)[:160]
        object_ref = (
            f"tenants/{context.security.tenant_id}/knowledge/{kb.id}/"
            f"documents/{document_id}/{version_id}/{sha256}/{safe_name}"
        )
        document = Document(
            id=document_id,
            tenant_id=context.security.tenant_id,
            knowledge_base_id=kb.id,
            title=file_name,
            classification=classification,
            owner_id=context.security.actor_id,
            acl_tokens=acl_tokens,
        )
        version = DocumentVersion(
            id=version_id,
            tenant_id=context.security.tenant_id,
            document_id=document.id,
            version_number=1,
            object_ref=object_ref,
            file_name=file_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            parser_version="parser-v1",
            chunk_strategy_version="fixed-800-overlap-100-v1",
        )
        self._repository.save_document(document)
        self._repository.save_document_version(version)
        upload_url = self._storage.create_upload(object_ref, size_bytes, mime_type)
        return document, version, upload_url

    def process_document(
        self, context: RequestContext, document_version_id: str
    ) -> IndexVersion:
        version = self._repository.get_document_version(
            context.security.tenant_id, document_version_id
        )
        if version is None:
            raise ResourceNotVisibleError()
        if version.status is DocumentStatus.INDEXED and version.index_version_id:
            existing_index = self._repository.get_index_version(
                context.security.tenant_id, version.index_version_id
            )
            if existing_index is not None:
                return existing_index
        document = self._repository.get_document(
            context.security.tenant_id, version.document_id
        )
        if document is None or document.status is DocumentStatus.REVOKED:
            raise ResourceNotVisibleError()
        content = self._storage.read(version.object_ref)
        if len(content) != version.size_bytes or hashlib.sha256(content).hexdigest() != version.sha256:
            quarantined = replace(document, status=DocumentStatus.QUARANTINED)
            self._repository.save_document(quarantined)
            raise FileSecurityBlockedError()
        if not self._matches_mime_signature(content, version.mime_type):
            self._repository.save_document(
                replace(document, status=DocumentStatus.QUARANTINED)
            )
            raise FileSecurityBlockedError()
        try:
            self._scanner.scan(version.object_ref, content)
        except FileSecurityBlockedError:
            self._repository.save_document(
                replace(document, status=DocumentStatus.QUARANTINED)
            )
            raise
        pages = self._parser.parse(content, version.mime_type)
        chunks = self._chunk(document, version, pages)
        self._repository.save_chunks(chunks)
        corpus = self._repository.list_chunks(
            context.security.tenant_id, document.knowledge_base_id
        )
        vectors = self._embedding.embed(tuple(chunk.content for chunk in corpus))
        if len(vectors) != len(corpus):
            raise InvalidArgumentError("embedding result count mismatch")
        version_number = self._repository.next_index_version_number(
            context.security.tenant_id, document.knowledge_base_id
        )
        index_fingerprint = hashlib.sha256(
            (
                f"{document.knowledge_base_id}:{version_number}:"
                f"{self._embedding.model_version}"
            ).encode("utf-8")
        ).hexdigest()[:40]
        index = IndexVersion(
            id=f"index_{index_fingerprint}",
            tenant_id=context.security.tenant_id,
            knowledge_base_id=document.knowledge_base_id,
            version_number=version_number,
            embedding_model_version=self._embedding.model_version,
            parser_version=version.parser_version,
            chunk_strategy_version=version.chunk_strategy_version,
            status=IndexStatus.BUILDING,
            chunk_count=len(corpus),
        )
        self._vector_index.upsert(
            tenant_id=context.security.tenant_id,
            knowledge_base_id=document.knowledge_base_id,
            index_version_id=index.id,
            chunks=corpus,
            vectors=vectors,
        )
        ready = replace(index, status=IndexStatus.READY)
        self._repository.save_index_version(ready)
        self._repository.save_document_version(
            replace(
                version,
                status=DocumentStatus.INDEXED,
                index_version_id=ready.id,
            )
        )
        self._repository.save_document(replace(document, status=DocumentStatus.INDEXED))
        return ready

    def publish_index(
        self, context: RequestContext, knowledge_base_id: str, index_id: str
    ) -> KnowledgeBase:
        kb = self._require_kb(context, knowledge_base_id)
        index = self._repository.get_index_version(context.security.tenant_id, index_id)
        if (
            index is None
            or index.knowledge_base_id != kb.id
            or index.status is not IndexStatus.READY
        ):
            raise IndexVersionUnavailableError()
        published_index = replace(index, status=IndexStatus.PUBLISHED)
        published_kb = kb.publish_index(index.id)
        self._repository.publish_index(published_kb, published_index)
        return published_kb

    def retrieve(
        self,
        context: RequestContext,
        *,
        api_code: str,
        query: str,
        top_k: int,
        generate_answer: bool,
        fail_on_insufficient_evidence: bool,
    ) -> KnowledgeResult:
        try:
            result = self._retrieve(
                context,
                api_code=api_code,
                query=query,
                top_k=top_k,
                generate_answer=generate_answer,
            )
        except AppError as exc:
            self._record_audit(context, api_code, "DENIED", exc.code)
            raise
        except Exception:
            self._record_audit(context, api_code, "FAILED", "INTERNAL_ERROR")
            raise
        if not result.sufficient_evidence and fail_on_insufficient_evidence:
            self._record_audit(
                context, api_code, "DENIED", "INSUFFICIENT_EVIDENCE"
            )
            raise InsufficientEvidenceError()
        self._record_audit(
            context,
            api_code,
            "SUCCESS",
            result_count=len(result.evidence),
            payload={
                "index_version_id": result.index_version_id,
                "candidate_count": result.candidate_count,
                "authorized_count": result.authorized_count,
                "generated": result.generated,
            },
        )
        return result

    def _retrieve(
        self,
        context: RequestContext,
        *,
        api_code: str,
        query: str,
        top_k: int,
        generate_answer: bool,
    ) -> KnowledgeResult:
        self._guard.validate_query(query)
        if not 1 <= top_k <= 50:
            raise InvalidArgumentError("top_k must be between 1 and 50")
        kb = self._repository.get_knowledge_base_by_code(
            context.security.tenant_id, api_code
        )
        if kb is None:
            raise ResourceNotVisibleError()
        if context.security.purpose not in kb.allowed_purposes:
            raise PolicyDeniedError(["PURPOSE_NOT_ALLOWED"])
        if top_k > kb.max_top_k:
            raise InvalidArgumentError("top_k exceeds the published API contract")
        if kb.active_index_version_id is None:
            raise IndexVersionUnavailableError()
        index = self._repository.get_index_version(
            context.security.tenant_id, kb.active_index_version_id
        )
        if index is None or index.status is not IndexStatus.PUBLISHED:
            raise IndexVersionUnavailableError()
        acl_tokens = self._subject_acl_tokens(context)
        query_vector = self._embedding.embed((query,))[0]
        candidates = self._vector_index.search(
            tenant_id=context.security.tenant_id,
            knowledge_base_id=kb.id,
            index_version_id=index.id,
            vector=query_vector,
            acl_tokens=acl_tokens,
            limit=min(top_k * 4, 100),
        )
        chunks = self._repository.get_authorized_chunks(
            context.security.tenant_id,
            tuple(hit.chunk_id for hit in candidates),
            acl_tokens,
        )
        score_by_id = {hit.chunk_id: hit.score for hit in candidates}
        safe_chunks = tuple(
            chunk
            for chunk in chunks
            if not self._guard.is_suspicious(chunk.content)
        )[:top_k]
        evidence = tuple(
            Evidence(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_version_id=chunk.document_version_id,
                title=str(chunk.metadata.get("title", "Document")),
                excerpt=chunk.content[:500],
                score=score_by_id.get(chunk.id, 0.0),
                page_number=chunk.page_number,
                classification=chunk.classification,
            )
            for chunk in safe_chunks
            if score_by_id.get(chunk.id, 0.0) > 0
        )
        sufficient = bool(evidence)
        can_egress = all(
            item.classification in {"PUBLIC", "INTERNAL"} for item in safe_chunks
        )
        generated = bool(
            sufficient and generate_answer and kb.allow_generation and can_egress
        )
        answer = self._generation.generate(query, safe_chunks) if generated else None
        return KnowledgeResult(
            answer=answer,
            sufficient_evidence=sufficient,
            evidence=evidence,
            knowledge_base_id=kb.id,
            index_version_id=index.id,
            candidate_count=len(candidates),
            authorized_count=len(chunks),
            generated=generated,
        )

    def _chunk(
        self,
        document: Document,
        version: DocumentVersion,
        pages: tuple[dict[str, object], ...],
    ) -> tuple[Chunk, ...]:
        result: list[Chunk] = []
        for page in pages:
            text = str(page.get("text", "")).strip()
            start = 0
            while start < len(text):
                end = min(len(text), start + 800)
                value = text[start:end].strip()
                if value:
                    content_hash = hashlib.sha256(value.encode("utf-8")).hexdigest()
                    chunk_fingerprint = hashlib.sha256(
                        f"{version.id}:{len(result)}:{content_hash}".encode("utf-8")
                    ).hexdigest()[:40]
                    result.append(
                        Chunk(
                            id=f"chunk_{chunk_fingerprint}",
                            tenant_id=document.tenant_id,
                            knowledge_base_id=document.knowledge_base_id,
                            document_id=document.id,
                            document_version_id=version.id,
                            ordinal=len(result),
                            content=value,
                            content_hash=content_hash,
                            acl_tokens=document.acl_tokens,
                            classification=document.classification,
                            page_number=int(page.get("page_number", 1)),
                            start_offset=start,
                            end_offset=end,
                            metadata={"title": document.title},
                        )
                    )
                if end == len(text):
                    break
                start = end - 100
        if not result:
            raise InvalidArgumentError("parser produced no usable document content")
        return tuple(result)

    @staticmethod
    def _matches_mime_signature(content: bytes, mime_type: str) -> bool:
        signatures = {
            "application/pdf": lambda: content.startswith(b"%PDF-"),
            "image/png": lambda: content.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg": lambda: content.startswith(b"\xff\xd8\xff"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": lambda: content.startswith(b"PK"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": lambda: content.startswith(b"PK"),
            "text/plain": lambda: b"\x00" not in content[:4096],
        }
        return bool(signatures[mime_type]())

    @staticmethod
    def _subject_acl_tokens(context: RequestContext) -> frozenset[str]:
        values = {"tenant:all", f"actor:{context.security.actor_id}"}
        delegated = context.security.delegated_user_id
        if delegated:
            values.add(f"user:{delegated}")
        department = context.security.attributes.get("department_id")
        if department:
            values.add(f"department:{department}")
        return frozenset(values)

    def _require_kb(self, context: RequestContext, kb_id: str) -> KnowledgeBase:
        value = self._repository.get_knowledge_base(context.security.tenant_id, kb_id)
        if value is None:
            raise ResourceNotVisibleError()
        return value

    def _record_audit(
        self,
        context: RequestContext,
        api_code: str,
        outcome: str,
        error_code: str | None = None,
        result_count: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._audit.record(
            AuditEvent.create(
                tenant_id=context.security.tenant_id,
                trace_id=context.trace_id,
                actor_type=context.security.actor_type.value,
                actor_id=context.security.actor_id,
                action="KNOWLEDGE_API_INVOKE",
                resource_type="KNOWLEDGE_API_VERSION",
                resource_id=api_code,
                purpose=context.security.purpose,
                outcome=outcome,
                error_code=error_code,
                result_count=result_count,
                payload=payload,
            )
        )
