import pytest

from splunk_soar_mcp.app import SoarApp
from splunk_soar_mcp.config import Mode, Settings

BASE = "https://soar.test"


def make_settings(**overrides) -> Settings:
    values = {
        "SPLUNK_SOAR_URL": BASE,
        "SPLUNK_SOAR_API": "test-token",
        "SOAR_MCP_MODE": "standard",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
async def app(settings):
    instance = SoarApp(settings)
    yield instance
    await instance.aclose()


@pytest.fixture
def modes():
    return Mode
