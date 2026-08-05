"""Composition root assembling domain services and infrastructure adapters."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine

from agent_data_os.application.query_service import QueryApplicationService
from agent_data_os.application.ingestion_service import IngestionApplicationService
from agent_data_os.application.knowledge_service import KnowledgeApplicationService
from agent_data_os.core.config import Settings
from agent_data_os.domains.data_service.models import QueryApiDefinition
from agent_data_os.domains.policy.models import Grant
from agent_data_os.domains.policy.service import PolicyEvaluator
from agent_data_os.infrastructure.memory import (
    InMemoryAuditRecorder,
    InMemoryPolicyRepository,
    InMemoryQueryApiRepository,
    InMemoryQueryDataPort,
    InMemoryIngestionStore,
)
from agent_data_os.infrastructure.connectors import (
    DevelopmentSchemaDiscovery,
    RejectingSecretResolver,
    SqlAlchemySchemaDiscovery,
    SecretResolver,
)
from agent_data_os.infrastructure.persistence.database import (
    build_engine,
    build_session_factory,
    initialize_schema,
)
from agent_data_os.infrastructure.persistence.repositories import (
    SqlAlchemyAuditRecorder,
    SqlAlchemyPolicyRepository,
    SqlAlchemyQueryApiRepository,
)
from agent_data_os.infrastructure.persistence.ingestion import (
    SqlAlchemyIngestionCommitter,
    SqlAlchemyIngestionRepository,
    SqlAlchemyServingQueryDataPort,
)
from agent_data_os.infrastructure.knowledge import (
    BasicFileSecurityScanner,
    DeterministicEmbedding,
    DevelopmentDocumentParser,
    DevelopmentGeneration,
    InMemoryKnowledgeRepository,
    InMemoryObjectStorage,
    InMemoryVectorIndex,
    UnavailableKnowledgeAdapter,
)
from agent_data_os.domains.knowledge.ports import (
    DocumentParser,
    EmbeddingPort,
    FileSecurityScanner,
    GenerationPort,
    ObjectStoragePort,
    VectorIndexPort,
)
from agent_data_os.infrastructure.persistence.knowledge import (
    ContentCipher,
    DevelopmentContentCipher,
    RejectingContentCipher,
    SqlAlchemyKnowledgeRepository,
)


@dataclass(slots=True)
class Container:
    settings: Settings
    policy_service: PolicyEvaluator
    query_service: QueryApplicationService
    ingestion_service: IngestionApplicationService
    knowledge_service: KnowledgeApplicationService
    audit_recorder: object
    object_storage: ObjectStoragePort
    engine: Engine | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeInfrastructure:
    object_storage: ObjectStoragePort
    scanner: FileSecurityScanner
    parser: DocumentParser
    embedding: EmbeddingPort
    vector_index: VectorIndexPort
    generation: GenerationPort


def build_container(
    settings: Settings,
    secret_resolver: SecretResolver | None = None,
    knowledge_infrastructure: KnowledgeInfrastructure | None = None,
    content_cipher: ContentCipher | None = None,
) -> Container:
    """Build V1.0 dependencies.

    Development fixtures are isolated here so replacing them with PostgreSQL and
    a remote PDP does not change API or domain code.
    """

    definitions: dict[tuple[str, str], QueryApiDefinition] = {}
    datasets: dict[tuple[str, str], list[dict[str, object]]] = {}
    grants: list[Grant] = []

    if settings.environment in {"development", "test"}:
        definition = QueryApiDefinition(
            code="customer_receivable_query",
            version="1.0.0",
            dataset_id="dataset_receivable",
            selectable_fields=frozenset(
                {
                    "customer_name",
                    "region",
                    "overdue_amount",
                    "currency",
                    "overdue_days",
                }
            ),
            allowed_filters={
                "region": frozenset({"eq", "in"}),
                "overdue_days": frozenset({"eq", "gte", "lte"}),
                "overdue_amount": frozenset({"gte", "lte"}),
            },
            allowed_order_fields=frozenset({"overdue_amount", "overdue_days"}),
            allowed_purposes=frozenset({"sales_risk_followup"}),
            default_limit=settings.default_query_limit,
            maximum_limit=settings.max_query_limit,
            dataset_version=12,
            freshness_at="2026-08-04T01:00:00Z",
            quality_score=96.0,
            field_types={
                "customer_name": "string",
                "region": "string",
                "overdue_amount": "decimal",
                "currency": "string",
                "overdue_days": "integer",
            },
        )
        definitions[("tenant_001", definition.code)] = definition
        datasets[("tenant_001", definition.dataset_id)] = [
            {
                "customer_name": "华东示例客户A",
                "region": "EAST",
                "overdue_amount": "320000.00",
                "currency": "CNY",
                "overdue_days": 45,
            },
            {
                "customer_name": "华南示例客户B",
                "region": "SOUTH",
                "overdue_amount": "510000.00",
                "currency": "CNY",
                "overdue_days": 62,
            },
            {
                "customer_name": "华东示例客户C",
                "region": "EAST",
                "overdue_amount": "88000.00",
                "currency": "CNY",
                "overdue_days": 12,
            },
        ]
        grants.append(
            Grant(
                tenant_id="tenant_001",
                actor_id="sales_risk_agent",
                resource_type="DATA_API_VERSION",
                resource_id="customer_receivable_query:1.0.0",
                action="INVOKE",
                purposes=frozenset({"sales_risk_followup"}),
                region_from_subject=True,
                max_rows=20,
            )
        )

    engine: Engine | None = None
    if settings.database_url:
        engine = build_engine(settings)
        initialize_schema(engine, settings)
        sessions = build_session_factory(engine)
        policy_repository = SqlAlchemyPolicyRepository(sessions)
        api_repository = SqlAlchemyQueryApiRepository(sessions)
        audit_recorder = SqlAlchemyAuditRecorder(sessions)
        ingestion_repository = SqlAlchemyIngestionRepository(sessions)
        ingestion_committer = SqlAlchemyIngestionCommitter(sessions)
        data_port = SqlAlchemyServingQueryDataPort(sessions)
        cipher = content_cipher or (
            DevelopmentContentCipher()
            if settings.environment in {"development", "test"}
            else RejectingContentCipher()
        )
        knowledge_repository = SqlAlchemyKnowledgeRepository(sessions, cipher)
    else:
        policy_repository = InMemoryPolicyRepository(grants)
        api_repository = InMemoryQueryApiRepository(definitions)
        audit_recorder = InMemoryAuditRecorder()
        ingestion_repository = InMemoryIngestionStore()
        ingestion_committer = ingestion_repository
        data_port = InMemoryQueryDataPort(datasets)
        knowledge_repository = InMemoryKnowledgeRepository()

    connector = (
        DevelopmentSchemaDiscovery()
        if settings.environment in {"development", "test"}
        else SqlAlchemySchemaDiscovery(secret_resolver or RejectingSecretResolver())
    )
    ingestion_service = IngestionApplicationService(
        ingestion_repository, connector, ingestion_committer
    )
    if knowledge_infrastructure is None:
        if settings.environment in {"development", "test"}:
            knowledge_infrastructure = KnowledgeInfrastructure(
                object_storage=InMemoryObjectStorage(),
                scanner=BasicFileSecurityScanner(),
                parser=DevelopmentDocumentParser(),
                embedding=DeterministicEmbedding(),
                vector_index=InMemoryVectorIndex(),
                generation=DevelopmentGeneration(),
            )
        else:
            unavailable = UnavailableKnowledgeAdapter()
            knowledge_infrastructure = KnowledgeInfrastructure(
                unavailable,
                unavailable,
                unavailable,
                unavailable,
                unavailable,
                unavailable,
            )
    knowledge_service = KnowledgeApplicationService(
        knowledge_repository,
        knowledge_infrastructure.object_storage,
        knowledge_infrastructure.scanner,
        knowledge_infrastructure.parser,
        knowledge_infrastructure.embedding,
        knowledge_infrastructure.vector_index,
        knowledge_infrastructure.generation,
        audit_recorder,
    )

    policy_service = PolicyEvaluator(policy_repository, policy_version=1)
    query_service = QueryApplicationService(
        api_repository,
        data_port,
        policy_service,
        audit_recorder,
    )
    return Container(
        settings,
        policy_service,
        query_service,
        ingestion_service,
        knowledge_service,
        audit_recorder,
        knowledge_infrastructure.object_storage,
        engine,
    )
