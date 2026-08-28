"""Shared runtime state handed to every tool module."""

from __future__ import annotations

from .client import SoarClient
from .config import Mode, Settings
from .errors import PermissionError_


class SoarApp:
    """Holds settings and lazily builds the REST client.

    The client is built on first use rather than at import time so that
    constructing the server (for ``--list-tools``, tests, or ``mcp dev``)
    never opens a socket.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: SoarClient | None = None

    @property
    def client(self) -> SoarClient:
        if self._client is None:
            self._client = SoarClient(self.settings)
        return self._client

    @property
    def mode(self) -> Mode:
        return self.settings.mode

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def require_label(self, label: str | None, *, what: str = "container") -> None:
        """Enforce SOAR_MCP_ALLOWED_LABELS before touching a tenant's data."""
        if not self.settings.label_permitted(label):
            allowed = ", ".join(sorted(self.settings.label_allowlist))
            raise PermissionError_(
                f"Refusing to modify {what} with label {label!r}. "
                f"SOAR_MCP_ALLOWED_LABELS permits only: {allowed}"
            )
