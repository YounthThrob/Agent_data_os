"""Read-only SQLAlchemy connector used for connection tests and schema discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from agent_data_os.core.errors import ConnectorUnavailableError
from agent_data_os.domains.ingestion.models import DataSource


@dataclass(frozen=True, slots=True)
class SecretValue:
    username: str
    password: str


class SecretResolver(Protocol):
    def resolve(self, secret_ref: str) -> SecretValue: ...


class RejectingSecretResolver:
    """Secure default until a Vault/KMS adapter is configured."""

    def resolve(self, secret_ref: str) -> SecretValue:
        raise ConnectorUnavailableError("secret resolver is not configured")


class SqlAlchemySchemaDiscovery:
    """Connect with resolved credentials without persisting or returning them."""

    DRIVER_NAMES = {
        "POSTGRESQL": "postgresql+psycopg",
        "MYSQL": "mysql+pymysql",
        "ORACLE": "oracle+oracledb",
    }

    def __init__(self, secrets: SecretResolver) -> None:
        self._secrets = secrets

    def _engine(self, source: DataSource) -> Engine:
        credentials = self._secrets.resolve(source.secret_ref)
        connection = source.connection
        try:
            url = URL.create(
                self.DRIVER_NAMES[source.source_type],
                username=credentials.username,
                password=credentials.password,
                host=str(connection["host"]),
                port=int(connection["port"]),
                database=str(connection["database"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConnectorUnavailableError("invalid connection metadata") from exc
        return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})

    def test_connection(self, source: DataSource) -> None:
        engine = self._engine(source)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise ConnectorUnavailableError("read-only connection test failed") from exc
        finally:
            engine.dispose()

    def discover(self, source: DataSource) -> tuple[dict[str, Any], ...]:
        engine = self._engine(source)
        objects: list[dict[str, Any]] = []
        try:
            inspector = inspect(engine)
            for schema_name in inspector.get_schema_names():
                if schema_name in {"information_schema", "pg_catalog"}:
                    continue
                for table_name in inspector.get_table_names(schema=schema_name):
                    columns = inspector.get_columns(table_name, schema=schema_name)
                    primary_key = inspector.get_pk_constraint(
                        table_name, schema=schema_name
                    ).get("constrained_columns", [])
                    objects.append(
                        {
                            "schema": schema_name,
                            "object": table_name,
                            "object_type": "TABLE",
                            "columns": [
                                {
                                    "name": column["name"],
                                    "type": str(column["type"]),
                                    "nullable": bool(column.get("nullable", True)),
                                }
                                for column in columns
                            ],
                            "primary_key": list(primary_key or []),
                        }
                    )
        except SQLAlchemyError as exc:
            raise ConnectorUnavailableError("schema discovery failed") from exc
        finally:
            engine.dispose()
        return tuple(objects)


class DevelopmentSchemaDiscovery:
    """Deterministic adapter for local demos; never selected in production."""

    def test_connection(self, source: DataSource) -> None:
        return None

    def discover(self, source: DataSource) -> tuple[dict[str, Any], ...]:
        return ()
