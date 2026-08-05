"""Database bootstrap and tenant-aware transaction helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from agent_data_os.core.config import Settings


def build_engine(settings: Settings) -> Engine:
    """Create the SQLAlchemy engine without performing schema mutations."""

    if not settings.database_url:
        raise ValueError("ADOS_DATABASE_URL is required for SQL persistence")
    options: dict[str, object] = {
        "pool_pre_ping": True,
        "echo": settings.database_echo,
    }
    if settings.database_url == "sqlite:///:memory:":
        options.update(
            connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    return create_engine(settings.database_url, **options)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return sessions with deterministic transaction/expiry behavior."""

    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def initialize_schema(engine: Engine, settings: Settings) -> None:
    """Create a local schema only when explicitly allowed outside production.

    Production deployments must apply versioned Alembic migrations instead.
    """

    if not settings.database_auto_create:
        return
    if settings.environment == "production":
        raise RuntimeError("automatic schema creation is forbidden in production")
    from agent_data_os.infrastructure.persistence.models import Base

    Base.metadata.create_all(engine)


@contextmanager
def tenant_session(
    session_factory: sessionmaker[Session], tenant_id: str
) -> Iterator[Session]:
    """Open a transaction scoped to one tenant.

    PostgreSQL receives a transaction-local setting consumed by RLS policies.
    Repositories additionally include explicit tenant predicates as a second
    isolation boundary and to keep SQLite integration tests representative.
    """

    with session_factory() as session, session.begin():
        session.info["tenant_id"] = tenant_id
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
                {"tenant_id": tenant_id},
            )
        yield session
