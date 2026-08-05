"""Encrypted knowledge repository, index publication and adapter tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import select

from agent_data_os.core.config import Settings
from agent_data_os.domains.knowledge.models import (
    Chunk,
    Document,
    DocumentStatus,
    DocumentVersion,
    IndexStatus,
    IndexVersion,
    KnowledgeBase,
)
from agent_data_os.infrastructure.knowledge import (
    DeepSeekGenerationGateway,
    MilvusVectorIndex,
)
from agent_data_os.infrastructure.persistence.database import (
    build_engine,
    build_session_factory,
    initialize_schema,
    tenant_session,
)
from agent_data_os.infrastructure.persistence.knowledge import (
    DevelopmentContentCipher,
    SqlAlchemyKnowledgeRepository,
)
from agent_data_os.infrastructure.persistence.models import KnowledgeChunkRow


@pytest.fixture()
def sessions():
    settings = Settings(
        environment="test",
        database_url="sqlite:///:memory:",
        database_auto_create=True,
    )
    engine = build_engine(settings)
    initialize_schema(engine, settings)
    factory = build_session_factory(engine)
    try:
        yield factory
    finally:
        engine.dispose()


def test_chunk_content_is_encrypted_and_acl_is_rechecked(sessions) -> None:
    repository = SqlAlchemyKnowledgeRepository(sessions, DevelopmentContentCipher())
    repository.save_knowledge_base(
        KnowledgeBase(
            "kb_1", "tenant_a", "policy", "Policy", "admin", frozenset({"review"})
        )
    )
    repository.save_document(
        Document(
            "doc_1",
            "tenant_a",
            "kb_1",
            "Policy",
            "INTERNAL",
            "admin",
            frozenset({"department:sales"}),
            DocumentStatus.INDEXED,
        )
    )
    repository.save_document_version(
        DocumentVersion(
            "dv_1",
            "tenant_a",
            "doc_1",
            1,
            "object/ref",
            "policy.txt",
            "text/plain",
            6,
            "a" * 64,
            "parser-v1",
            "chunk-v1",
        )
    )
    content = "secret policy content"
    chunk = Chunk(
        "chunk_1",
        "tenant_a",
        "kb_1",
        "doc_1",
        "dv_1",
        0,
        content,
        hashlib.sha256(content.encode()).hexdigest(),
        frozenset({"department:sales"}),
        "INTERNAL",
    )
    repository.save_chunks((chunk,))
    with tenant_session(sessions, "tenant_a") as session:
        row = session.scalar(select(KnowledgeChunkRow))
        assert content not in row.content_ciphertext

    assert repository.get_authorized_chunks(
        "tenant_a", ("chunk_1",), frozenset({"department:sales"})
    )[0].content == content
    assert repository.get_authorized_chunks(
        "tenant_a", ("chunk_1",), frozenset({"department:finance"})
    ) == ()
    assert repository.get_authorized_chunks(
        "tenant_b", ("chunk_1",), frozenset({"department:sales"})
    ) == ()


def test_blue_green_index_publish_retires_previous_version(sessions) -> None:
    repository = SqlAlchemyKnowledgeRepository(sessions, DevelopmentContentCipher())
    kb = KnowledgeBase(
        "kb_1", "tenant_a", "policy", "Policy", "admin", frozenset({"review"})
    )
    repository.save_knowledge_base(kb)
    first = IndexVersion(
        "index_1", "tenant_a", "kb_1", 1, "embed-v1", "parser-v1", "chunk-v1", IndexStatus.READY, 2
    )
    repository.save_index_version(first)
    repository.publish_index(kb.publish_index(first.id), IndexVersion(
        first.id, first.tenant_id, first.knowledge_base_id, first.version_number,
        first.embedding_model_version, first.parser_version, first.chunk_strategy_version,
        IndexStatus.PUBLISHED, first.chunk_count
    ))
    current_kb = repository.get_knowledge_base("tenant_a", "kb_1")
    second = IndexVersion(
        "index_2", "tenant_a", "kb_1", 2, "embed-v1", "parser-v1", "chunk-v1", IndexStatus.READY, 3
    )
    repository.save_index_version(second)
    repository.publish_index(current_kb.publish_index(second.id), IndexVersion(
        second.id, second.tenant_id, second.knowledge_base_id, second.version_number,
        second.embedding_model_version, second.parser_version, second.chunk_strategy_version,
        IndexStatus.PUBLISHED, second.chunk_count
    ))
    assert repository.get_index_version("tenant_a", "index_1").status is IndexStatus.RETIRED
    assert repository.get_index_version("tenant_a", "index_2").status is IndexStatus.PUBLISHED
    assert repository.get_knowledge_base("tenant_a", "kb_1").active_index_version_id == "index_2"


def test_milvus_adapter_always_applies_tenant_index_and_acl_filters() -> None:
    class Client:
        def __init__(self) -> None:
            self.filter = ""
            self.search_params = {}

        def search(self, **kwargs):
            self.filter = kwargs["filter"]
            self.search_params = kwargs["search_params"]
            return [[{"entity": {"chunk_id": "chunk_1"}, "distance": 0.9}]]

    client = Client()
    hits = MilvusVectorIndex(client, "ados_chunks").search(
        tenant_id="tenant_a",
        knowledge_base_id="kb_1",
        index_version_id="index_1",
        vector=(1.0, 0.0),
        acl_tokens=frozenset({"department:sales"}),
        limit=5,
    )
    assert hits[0].chunk_id == "chunk_1"
    assert 'tenant_id == "tenant_a"' in client.filter
    assert 'index_version_id == "index_1"' in client.filter
    assert "array_contains_any" in client.filter
    assert client.search_params == {"metric_type": "COSINE"}


def test_deepseek_gateway_uses_fixed_system_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "grounded answer"}}]}

    def fake_post(url: str, **kwargs):
        captured.update({"url": url, **kwargs})
        return Response()

    monkeypatch.setattr("agent_data_os.infrastructure.knowledge.httpx.post", fake_post)
    chunk = Chunk(
        "chunk_1",
        "tenant_a",
        "kb_1",
        "doc_1",
        "dv_1",
        0,
        "Policy evidence",
        "a" * 64,
        frozenset({"tenant:all"}),
        "INTERNAL",
    )
    gateway = DeepSeekGenerationGateway("runtime-secret")
    assert gateway.generate("What is the policy?", (chunk,)) == "grounded answer"
    messages = captured["json"]["messages"]
    assert "Policy evidence" not in messages[0]["content"]
    assert "untrusted data" in messages[0]["content"]
    assert "[evidence:chunk_1] Policy evidence" in messages[1]["content"]
    assert captured["headers"]["Authorization"] == "Bearer runtime-secret"


def test_iteration4_migration_enables_rls_for_knowledge_tables() -> None:
    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "20260805_0003_iteration4_knowledge_pipeline.py"
    ).read_text(encoding="utf-8")
    for table in (
        "knowledge_bases",
        "documents",
        "document_versions",
        "knowledge_chunks",
        "knowledge_index_versions",
    ):
        assert f'"{table}"' in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
