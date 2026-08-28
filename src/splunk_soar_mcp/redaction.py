"""Strip credentials out of anything on its way to the caller.

SOAR's REST API returns asset configuration verbatim, credentials included:
`/rest/asset` hands back populated `password`, `client_secret`, `api_key` and
`ph auth token` fields in plaintext. Anything this server returns may be read by
a language model, written to a transcript, and stored by whoever runs that
model, so secrets must not leave the process.

The rule is key-shaped, not value-shaped: a value is replaced when its *key*
looks like a credential. Guessing at values (high-entropy strings, base64) both
misses real secrets and destroys legitimate data like hashes and IDs.

This is a safety net over the whole response, not a substitute for not asking
for secrets in the first place.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "«redacted by splunk-soar-mcp»"

#: Substrings that mark a key as holding a credential. Matched against the key
#: with everything but letters and digits removed, so `ph auth token`,
#: `PH_AUTH_TOKEN` and `phAuthToken` all collapse to the same thing.
SENSITIVE_KEY_PARTS: tuple[str, ...] = (
    "password",
    "passwd",
    "pwd",
    "passphrase",
    "secret",
    "token",
    "apikey",
    "credential",
    "privatekey",
    "accesskey",
    "secretkey",
    "sessionkey",
    "clientsecret",
    "authcode",
    "bearer",
    "certificate",
    "privkey",
)

#: Keys that contain a sensitive substring but hold no secret. Without these,
#: `auth_token_type` or `has_password` would be redacted for no reason.
ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "tokenization",
        "haspassword",
        "passwordrequired",
        "passwordlastset",
        "tokenexpiry",
        "tokenexpiration",
        "tokentype",
        "authtokentype",
        "certificatename",
        "requirestoken",
    }
)

_NORMALISE = re.compile(r"[^a-z0-9]+")

#: Matches `"key": "value"` in a raw response body, for error text that never
#: gets parsed into a dict.
_KEY_ALTERNATION = "|".join(SENSITIVE_KEY_PARTS)
_JSON_PAIR = re.compile(
    r'("(?:[^"\\]|\\.)*?(?:' + _KEY_ALTERNATION + r')(?:[^"\\]|\\.)*?"\s*:\s*)'
    r'"(?:[^"\\]|\\.)*"',
    re.IGNORECASE,
)


def is_sensitive_key(key: str) -> bool:
    normalised = _NORMALISE.sub("", str(key).lower())
    if normalised in ALLOWED_KEYS:
        return False
    return any(part in normalised for part in SENSITIVE_KEY_PARTS)


def redact(value: Any) -> Any:
    """Return a copy of `value` with credential-shaped fields replaced.

    Walks dicts and lists. Scalars are returned unchanged — a bare string has no
    key to judge it by.
    """
    if isinstance(value, dict):
        return {
            key: REDACTED if is_sensitive_key(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


def redact_text(text: str) -> str:
    """Blank out `"key": "value"` pairs in an unparsed response body."""
    return _JSON_PAIR.sub(lambda m: f'{m.group(1)}"{REDACTED}"', text)
