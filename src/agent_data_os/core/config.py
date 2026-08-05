"""Environment configuration with secure defaults.

The project intentionally avoids hiding security-sensitive defaults in framework
magic. Production startup rejects development authentication explicitly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable runtime settings loaded from environment variables."""

    service_name: str = "agent-data-os"
    environment: str = "development"
    log_level: str = "INFO"
    allow_insecure_dev_auth: bool = False
    default_query_limit: int = 20
    max_query_limit: int = 100

    def validate(self) -> None:
        """Fail startup when a dangerous configuration reaches production."""

        if self.environment == "production" and self.allow_insecure_dev_auth:
            raise RuntimeError(
                "ADOS_ALLOW_INSECURE_DEV_AUTH must be false in production"
            )
        if self.default_query_limit < 1:
            raise RuntimeError("ADOS_DEFAULT_QUERY_LIMIT must be positive")
        if self.max_query_limit < self.default_query_limit:
            raise RuntimeError(
                "ADOS_MAX_QUERY_LIMIT must be greater than or equal to the default"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and validate settings once per process."""

    settings = Settings(
        service_name=os.getenv("ADOS_SERVICE_NAME", "agent-data-os"),
        environment=os.getenv("ADOS_ENVIRONMENT", "development").lower(),
        log_level=os.getenv("ADOS_LOG_LEVEL", "INFO").upper(),
        allow_insecure_dev_auth=_as_bool(
            os.getenv("ADOS_ALLOW_INSECURE_DEV_AUTH"), default=False
        ),
        default_query_limit=int(os.getenv("ADOS_DEFAULT_QUERY_LIMIT", "20")),
        max_query_limit=int(os.getenv("ADOS_MAX_QUERY_LIMIT", "100")),
    )
    settings.validate()
    return settings

