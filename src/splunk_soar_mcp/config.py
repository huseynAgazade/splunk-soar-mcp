"""Configuration and the safety model.

Credentials resolve in this order (first hit wins):
  1. process environment
  2. a ``.env`` file in the working directory
  3. a ``secrets.txt`` file (``$SOAR_SECRETS``, cwd, or any parent directory)

``secrets.txt`` uses the same ``KEY=value`` format as ``.env`` and exists so the
server can drop into an established Splunk SOAR workflow without a second copy
of the token.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Mode(str, Enum):
    """How much the server is allowed to do to the instance.

    The mode decides which tools are *registered*, not merely which ones
    refuse at call time — a ``readonly`` server does not expose a single
    mutating tool, so nothing can be talked into using one.
    """

    READONLY = "readonly"
    STANDARD = "standard"
    FULL = "full"

    @property
    def rank(self) -> int:
        return {"readonly": 0, "standard": 1, "full": 2}[self.value]

    def allows(self, required: "Mode") -> bool:
        return self.rank >= required.rank


def _find_secrets_file() -> Path | None:
    candidates: list[Path] = []
    if os.environ.get("SOAR_SECRETS"):
        candidates.append(Path(os.environ["SOAR_SECRETS"]))
    here = Path.cwd()
    candidates.append(here / "secrets.txt")
    candidates.extend(parent / "secrets.txt" for parent in here.parents)
    for path in candidates:
        if path.is_file():
            return path
    return None


def _load_secrets_fallback() -> None:
    """Populate missing SOAR env vars from a discovered ``secrets.txt``.

    Only fills gaps — anything already in the environment wins.
    """
    if os.environ.get("SPLUNK_SOAR_URL") and os.environ.get("SPLUNK_SOAR_API"):
        return
    path = _find_secrets_file()
    if path is None:
        return
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key in ("SPLUNK_SOAR_URL", "SPLUNK_SOAR_API") and not os.environ.get(key):
            os.environ[key] = value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    soar_url: str = Field(validation_alias="SPLUNK_SOAR_URL")
    soar_token: str = Field(validation_alias="SPLUNK_SOAR_API")

    mode: Mode = Field(default=Mode.STANDARD, validation_alias="SOAR_MCP_MODE")
    allowed_labels: str = Field(default="", validation_alias="SOAR_MCP_ALLOWED_LABELS")

    verify_ssl: bool = Field(default=True, validation_alias="SOAR_MCP_VERIFY_SSL")
    ca_bundle: str = Field(default="", validation_alias="SOAR_MCP_CA_BUNDLE")
    timeout: float = Field(default=60.0, validation_alias="SOAR_MCP_TIMEOUT")

    default_page_size: int = Field(default=25, validation_alias="SOAR_MCP_DEFAULT_PAGE_SIZE")
    max_page_size: int = Field(default=500, validation_alias="SOAR_MCP_MAX_PAGE_SIZE")

    @field_validator("soar_url")
    @classmethod
    def _normalise_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value.endswith("/rest"):
            value = value[: -len("/rest")]
        if not value.startswith(("http://", "https://")):
            raise ValueError("SPLUNK_SOAR_URL must start with http:// or https://")
        return value

    @property
    def label_allowlist(self) -> frozenset[str]:
        """Container labels this server may touch. Empty set means no restriction."""
        return frozenset(x.strip() for x in self.allowed_labels.split(",") if x.strip())

    @property
    def verify(self) -> bool | str:
        """The value httpx wants for ``verify``: a CA path beats a bare bool."""
        if self.ca_bundle:
            return self.ca_bundle
        return self.verify_ssl

    def label_permitted(self, label: str | None) -> bool:
        allow = self.label_allowlist
        if not allow:
            return True
        return label is not None and label in allow


def load_settings() -> Settings:
    _load_secrets_fallback()
    return Settings()  # type: ignore[call-arg]
