import pytest

from splunk_soar_mcp.redaction import REDACTED, is_sensitive_key, redact, redact_text


@pytest.mark.parametrize(
    "key",
    [
        "password", "Password", "ssh_password", "passwd", "pwd",
        "client_secret", "acme_client_secret_edr", "secret",
        "token", "auth_token", "ph_auth_token", "ph auth token",
        "MM_BOT_TOKEN", "bot_token", "edl_api_token",
        "api_key", "apikey", "API_KEY", "private_key", "passphrase",
    ],
)
def test_credential_keys_are_detected(key):
    assert is_sensitive_key(key)


@pytest.mark.parametrize(
    "key",
    ["name", "id", "url", "username", "auth_type", "hostname", "fileHash",
     "sourceAddress", "token_type", "has_password", "certificate_name"],
)
def test_ordinary_keys_are_left_alone(key):
    assert not is_sensitive_key(key)


def test_asset_configuration_is_redacted():
    asset = {
        "id": 12,
        "name": "prod_crowdstrike",
        "configuration": {
            "base_url": "https://api.example.com",
            "client_id": "abc123",
            "client_secret": "SUPER-SECRET-VALUE",
            "ph auth token": "tok_live_xyz",
        },
    }
    out = redact(asset)
    assert out["name"] == "prod_crowdstrike"
    assert out["configuration"]["base_url"] == "https://api.example.com"
    assert out["configuration"]["client_id"] == "abc123"
    assert out["configuration"]["client_secret"] == REDACTED
    assert out["configuration"]["ph auth token"] == REDACTED
    assert "SUPER-SECRET-VALUE" not in str(out)
    assert "tok_live_xyz" not in str(out)


def test_redaction_reaches_into_lists():
    out = redact({"data": [{"password": "hunter2"}, {"ok": "fine"}]})
    assert out["data"][0]["password"] == REDACTED
    assert out["data"][1]["ok"] == "fine"


def test_the_original_object_is_not_mutated():
    asset = {"configuration": {"password": "hunter2"}}
    redact(asset)
    assert asset["configuration"]["password"] == "hunter2"


def test_scalars_pass_through():
    assert redact("plain") == "plain"
    assert redact(42) == 42
    assert redact(None) is None


def test_raw_response_text_is_scrubbed():
    body = '{"name": "x", "password": "hunter2", "id": 4}'
    out = redact_text(body)
    assert "hunter2" not in out
    assert '"name": "x"' in out
    assert '"id": 4' in out


@pytest.mark.parametrize("key", ["google_maps_key", "ssh_key", "signing_key", "hmac_key"])
def test_trailing_key_is_treated_as_a_credential(key):
    assert is_sensitive_key(key)


@pytest.mark.parametrize("key", ["conditionKey", "comparisonKey", "sort_key", "cef_key", "key"])
def test_structural_keys_are_not_redacted(key):
    # The visual editor's node format uses conditionKey/comparisonKey; redacting
    # them would corrupt a decoded block.
    assert not is_sensitive_key(key)


def test_decoded_vpe_block_survives_redaction():
    node = {"conditions": [{"conditionKey": "condition_key_0",
                            "comparisons": [{"comparisonKey": "comparison_key_0",
                                             "op": "==", "param": "x", "value": "1"}]}]}
    assert redact(node) == node
