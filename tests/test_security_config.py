"""Configuration tests ensure development authentication cannot reach production."""

import pytest

from agent_data_os.core.config import Settings
from agent_data_os.main import create_app


def test_production_rejects_development_authentication() -> None:
    settings = Settings(environment="production", allow_insecure_dev_auth=True)
    with pytest.raises(RuntimeError, match="must be false in production"):
        create_app(settings)

