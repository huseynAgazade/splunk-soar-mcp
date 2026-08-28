import pytest
from pydantic import ValidationError

from splunk_soar_mcp.config import Mode

from conftest import make_settings


def test_mode_ranking():
    assert Mode.FULL.allows(Mode.READONLY)
    assert Mode.STANDARD.allows(Mode.STANDARD)
    assert not Mode.READONLY.allows(Mode.STANDARD)
    assert not Mode.STANDARD.allows(Mode.FULL)


@pytest.mark.parametrize(
    "given,expected",
    [
        ("https://soar.test/", "https://soar.test"),
        ("https://soar.test/rest", "https://soar.test"),
        ("https://soar.test:8443/rest/", "https://soar.test:8443"),
    ],
)
def test_url_is_normalised(given, expected):
    assert make_settings(SPLUNK_SOAR_URL=given).soar_url == expected


def test_url_without_scheme_is_rejected():
    with pytest.raises(ValidationError):
        make_settings(SPLUNK_SOAR_URL="soar.test")


def test_empty_allowlist_permits_everything():
    settings = make_settings()
    assert settings.label_permitted("anything")
    assert settings.label_permitted(None)


def test_allowlist_restricts_labels():
    settings = make_settings(SOAR_MCP_ALLOWED_LABELS="lab, test_label")
    assert settings.label_allowlist == frozenset({"lab", "test_label"})
    assert settings.label_permitted("lab")
    assert not settings.label_permitted("production")
    assert not settings.label_permitted(None)


def test_ca_bundle_beats_verify_flag():
    settings = make_settings(SOAR_MCP_VERIFY_SSL="false", SOAR_MCP_CA_BUNDLE="/tmp/ca.pem")
    assert settings.verify == "/tmp/ca.pem"
