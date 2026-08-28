"""Shared runtime state handed to every tool module."""

from __future__ import annotations

import json

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
        """Enforce SOAR_MCP_ALLOWED_LABELS before touching a tenant's data.

        The refusal names neither the target's label nor the permitted set. On a
        multi-tenant instance the allowlist *is* the customer list, and an error
        message is an answer — repeated calls would otherwise enumerate every
        tenant the deployment knows about.
        """
        if not self.settings.label_permitted(label):
            raise PermissionError_(
                f"This deployment is scoped to a subset of container labels, and "
                f"this {what} is outside it. That is a deployment restriction, "
                f"not a transient error — do not retry, and do not try to reach "
                f"the same data another way."
            )

    def label_filter(self) -> dict[str, str]:
        """Query parameters restricting a container listing to permitted labels.

        Empty when no allowlist is configured, so an unrestricted deployment
        pays nothing for this.
        """
        allow = self.settings.label_allowlist
        if not allow:
            return {}
        return {"_filter_label__in": json.dumps(sorted(allow))}

    async def guarded_container(self, container_id: int) -> dict:
        """Fetch a container, refusing if its label is outside the allowlist.

        Reads go through this as well as writes: on a scoped deployment, being
        able to read another tenant's case is the disclosure, not just being
        able to change it.
        """
        record = await self.client.get(f"container/{int(container_id)}")
        self.require_label(record.get("label"))
        return record
