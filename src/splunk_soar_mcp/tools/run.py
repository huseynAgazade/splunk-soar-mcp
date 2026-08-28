"""Execution — running playbooks and app actions. Registered only in `full` mode."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ..app import SoarApp
from ..formatting import to_json

EXECUTE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True
)


def register(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.tool(
        title="Run playbook",
        annotations=EXECUTE,
        description=(
            "Run a playbook against a container. This executes real automation — it "
            "can contain, block or notify. Confirm with the operator before calling. "
            "Returns the playbook_run id; poll it with soar_get_playbook_run."
        ),
    )
    async def soar_run_playbook(
        playbook_ref: str, container_id: int, scope: str = "new"
    ) -> str:
        """Execute a playbook.

        Args:
            playbook_ref: Playbook id or name fragment.
            container_id: The container to run against.
            scope: "new" for artifacts not yet processed, "all" for every artifact.
        """
        container_id = int(container_id)
        await app.guarded_container(container_id)
        playbook_id = await app.client.resolve_id("playbook", playbook_ref, label="playbook")
        result = await app.client.post(
            "playbook_run",
            {
                "container_id": container_id,
                "playbook_id": playbook_id,
                "scope": scope,
                "run": True,
            },
        )
        return f"Started playbook {playbook_id} on container {container_id}.\n{to_json(result)}"

    @mcp.tool(
        title="Run app action",
        annotations=EXECUTE,
        description=(
            "Run a single app action against an asset. This performs a real "
            "integration call — it can block an IP, isolate a host or send mail. "
            "Confirm with the operator before calling. Check the action's parameters "
            "with soar_get_app_action first."
        ),
    )
    async def soar_run_action(
        action: str,
        asset: str,
        container_id: int,
        parameters: dict[str, Any] | None = None,
        name: str | None = None,
    ) -> str:
        """Execute an app action.

        Args:
            action: Action name exactly as the app exposes it, e.g. "block ip".
            asset: Asset name or id to run against.
            container_id: Container the run is recorded against.
            parameters: Action parameters, e.g. {"ip": "1.2.3.4"}.
            name: Optional label for the run, shown in the action-run list.
        """
        container_id = int(container_id)
        await app.guarded_container(container_id)
        asset_record = await app.client.resolve("asset", asset, label="asset")
        payload = {
            "action": action,
            "container_id": container_id,
            "name": name or f"mcp: {action}",
            "targets": [
                {
                    "assets": [asset_record["name"]],
                    "parameters": [parameters or {}],
                }
            ],
        }
        result = await app.client.post("action_run", payload)
        return (
            f"Started action {action!r} on asset {asset_record['name']!r} "
            f"(container {container_id}).\n{to_json(result)}"
        )
