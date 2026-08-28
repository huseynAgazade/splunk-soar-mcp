"""Raw REST access — the escape hatch for endpoints without a dedicated tool."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ..app import SoarApp
from ..formatting import to_json

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)


def register(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.tool(
        title="Raw REST GET",
        annotations=READ,
        description=(
            "GET any SOAR REST path, for endpoints without a dedicated tool. `path` "
            "is relative to /rest, e.g. 'ph_user' or 'container/42/attachments'. "
            "Filters use SOAR's syntax and need literal quotes around the value: "
            '_filter_name__icontains=\'"triage"\'.'
        ),
    )
    async def soar_rest_get(path: str, params: dict[str, Any] | None = None) -> str:
        """Perform a raw GET.

        Args:
            path: REST path relative to /rest, without a leading slash.
            params: Query parameters, e.g. {"page_size": 5, "sort": "id"}.
        """
        return to_json(await app.client.get(path, **(params or {})))


def register_writes(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.tool(
        title="Raw REST POST",
        annotations=WRITE,
        description=(
            "POST to any SOAR REST path. This can create or modify anything on the "
            "instance and bypasses every guard the dedicated tools apply — including "
            "the container label allowlist. Prefer a specific tool when one exists."
        ),
    )
    async def soar_rest_post(path: str, payload: dict[str, Any]) -> str:
        """Perform a raw POST.

        Args:
            path: REST path relative to /rest, without a leading slash.
            payload: JSON body.
        """
        return to_json(await app.client.post(path, payload))

    @mcp.tool(
        title="Raw REST DELETE",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
        description=(
            "DELETE any SOAR REST path. Permanent, and bypasses every guard the "
            "dedicated tools apply. Confirm with the operator before calling."
        ),
    )
    async def soar_rest_delete(path: str) -> str:
        """Perform a raw DELETE.

        Args:
            path: REST path relative to /rest, without a leading slash.
        """
        return to_json(await app.client.delete(path))
