"""Configuration and the safety model.

Credentials come from the process environment, or from an env file — the
standard twelve-factor arrangement. For an MCP client that launches this server
over stdio, the natural place is the ``env`` block of the client's own server
config; for an HTTP deployment, real environment variables or a secret manager.

``SOAR_MCP_ENV_FILE`` overrides which env file is read, since a stdio server
inherits its working directory from whatever launched it and a relative default
is not always the file you meant.
"""

from __future__ import annotations

import os
from enum import Enum

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

    def allows(self, required: Mode) -> bool:
        return self.rank >= required.rank


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.environ.get("SOAR_MCP_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
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
    return Settings()  # type: ignore[call-arg]
