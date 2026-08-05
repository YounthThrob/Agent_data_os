"""Identity resolution ports and a development-only adapter."""

from __future__ import annotations

from typing import Protocol

from agent_data_os.core.config import Settings
from agent_data_os.core.context import ActorType, SecurityContext
from agent_data_os.core.errors import UnauthenticatedError


class IdentityResolver(Protocol):
    """Converts an authenticated transport credential into trusted identity data."""

    def resolve(self, authorization: str | None, purpose: str | None) -> SecurityContext:
        ...


class RejectingIdentityResolver:
    """Secure placeholder used until a production OIDC adapter is configured."""

    def resolve(self, authorization: str | None, purpose: str | None) -> SecurityContext:
        raise UnauthenticatedError("生产身份解析器尚未配置")


class DevelopmentIdentityResolver:
    """Parse a non-cryptographic local token.

    Token format: ``dev.<tenant>.<actor_type>.<actor_id>.<region>``.
    This adapter is deliberately unavailable in production.
    """

    def __init__(self, settings: Settings) -> None:
        if settings.environment == "production":
            raise RuntimeError("DevelopmentIdentityResolver is forbidden in production")

    def resolve(self, authorization: str | None, purpose: str | None) -> SecurityContext:
        if not purpose:
            raise UnauthenticatedError("数据接口必须提供X-Purpose")
        if not authorization or not authorization.startswith("Bearer "):
            raise UnauthenticatedError()

        token = authorization.removeprefix("Bearer ").strip()
        parts = token.split(".")
        if len(parts) != 5 or parts[0] != "dev":
            raise UnauthenticatedError("开发Token格式无效")

        _, tenant_id, actor_type_value, actor_id, region = parts
        try:
            actor_type = ActorType(actor_type_value.upper())
        except ValueError as exc:
            raise UnauthenticatedError("未知主体类型") from exc

        return SecurityContext(
            tenant_id=tenant_id,
            actor_type=actor_type,
            actor_id=actor_id,
            purpose=purpose,
            agent_version="dev-1.0" if actor_type is ActorType.AGENT else None,
            attributes={"region": region},
            scopes=frozenset({"data_api:invoke"}),
        )


def build_identity_resolver(settings: Settings) -> IdentityResolver:
    """Select an adapter without silently enabling insecure production auth."""

    if settings.allow_insecure_dev_auth:
        return DevelopmentIdentityResolver(settings)
    return RejectingIdentityResolver()

