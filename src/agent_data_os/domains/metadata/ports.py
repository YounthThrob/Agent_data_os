"""Repository ports for tenant-scoped metadata aggregates."""

from __future__ import annotations

from typing import Protocol

from agent_data_os.domains.metadata.models import (
    AgentMetadata,
    DataApiMetadata,
    Tenant,
    UserAccount,
)


class MetadataRepository(Protocol):
    def add_tenant(self, tenant: Tenant) -> None:
        ...

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        ...

    def add_user(self, user: UserAccount) -> None:
        ...

    def get_user(self, tenant_id: str, user_id: str) -> UserAccount | None:
        ...

    def add_agent(self, agent: AgentMetadata) -> None:
        ...

    def get_agent(self, tenant_id: str, agent_id: str) -> AgentMetadata | None:
        ...

    def add_data_api(self, data_api: DataApiMetadata) -> None:
        ...

    def get_data_api(
        self, tenant_id: str, api_id: str
    ) -> DataApiMetadata | None:
        ...
