"""Discovery: what this SOAR instance actually has installed."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ..app import SoarApp
from ..formatting import details, listing, table, to_json

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)


def register(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.tool(
        title="List apps",
        annotations=READ,
        description=(
            "List installed SOAR apps (integrations), optionally filtered by a name "
            "fragment. Use this to find the app id needed by soar_list_app_actions."
        ),
    )
    async def soar_list_apps(
        query: str | None = None, page_size: int | None = None, as_json: bool = False
    ) -> str:
        """List installed apps.

        Args:
            query: Case-insensitive name fragment, e.g. "crowdstrike". Omit for all.
            page_size: Rows to return (default 25).
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.search("app", query, page_size=page_size)
        return listing(
            payload,
            ["id", "name", "publisher", "app_version", "python_version", "disabled"],
            as_json=as_json,
            empty="No apps matched.",
        )

    @mcp.tool(
        title="List app actions",
        annotations=READ,
        description=(
            "List the actions an app exposes, with their descriptions. Accepts an app "
            "id or a name fragment. This is how you learn the exact action name and "
            "parameters an action block needs."
        ),
    )
    async def soar_list_app_actions(app_ref: str, as_json: bool = False) -> str:
        """List an app's actions.

        Args:
            app_ref: App id (e.g. "241") or name fragment (e.g. "crowdstrike").
            as_json: Return full JSON records instead of a table.
        """
        app_id = await app.client.resolve_id("app", app_ref, label="app")
        payload = await app.client.get(f"app/{app_id}/actions", page_size=200)
        rows = payload.get("data") or []
        if as_json:
            return to_json(rows)
        return f"app id={app_id}\n\n" + table(
            rows, ["id", "action", "type", "description"], empty="This app exposes no actions."
        )

    @mcp.tool(
        title="Get app action parameters",
        annotations=READ,
        description=(
            "Return the full definition of one app action — every parameter with its "
            "type, whether it is required, allowed values, and the output datapaths "
            "the action produces. Read this before writing an action block."
        ),
    )
    async def soar_get_app_action(app_ref: str, action_name: str) -> str:
        """Describe a single action in full.

        Args:
            app_ref: App id or name fragment.
            action_name: The action's name, e.g. "detonate file".
        """
        app_id = await app.client.resolve_id("app", app_ref, label="app")
        payload = await app.client.get(f"app/{app_id}/actions", page_size=200)
        wanted = action_name.strip().lower()
        matches = [
            a
            for a in payload.get("data") or []
            if str(a.get("action", "")).lower() == wanted
        ] or [
            a for a in payload.get("data") or [] if wanted in str(a.get("action", "")).lower()
        ]
        if not matches:
            return f"No action matching {action_name!r} on app id={app_id}."
        return to_json(matches[0])

    @mcp.tool(
        title="List assets",
        annotations=READ,
        description=(
            "List configured assets (an asset is one configured instance of an app — "
            "the thing an action block actually runs against)."
        ),
    )
    async def soar_list_assets(
        query: str | None = None, page_size: int | None = None, as_json: bool = False
    ) -> str:
        """List assets.

        Args:
            query: Case-insensitive name fragment. Omit for all.
            page_size: Rows to return (default 25).
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.search("asset", query, page_size=page_size)
        return listing(
            payload,
            ["id", "name", "app", "type", "primary_users", "disabled"],
            as_json=as_json,
            empty="No assets matched.",
        )

    @mcp.tool(
        title="Get asset",
        annotations=READ,
        description=(
            "Full configuration of one asset, including its app, tenants and "
            "non-secret configuration values."
        ),
    )
    async def soar_get_asset(asset_ref: str) -> str:
        """Show one asset.

        Args:
            asset_ref: Asset id or name fragment.
        """
        record = await app.client.resolve("asset", asset_ref, label="asset")
        return to_json(record)

    @mcp.tool(
        title="List custom functions",
        annotations=READ,
        description=(
            "List custom functions available to playbooks. Prefer an existing custom "
            "function over new custom code in a playbook block."
        ),
    )
    async def soar_list_custom_functions(
        query: str | None = None, page_size: int | None = None, as_json: bool = False
    ) -> str:
        """List custom functions.

        Args:
            query: Case-insensitive name fragment. Omit for all.
            page_size: Rows to return (default 25).
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.search("custom_function", query, page_size=page_size)
        return listing(
            payload,
            ["id", "name", "scm", "description", "disabled"],
            as_json=as_json,
            empty="No custom functions matched.",
        )

    @mcp.tool(
        title="Get custom function",
        annotations=READ,
        description=(
            "Full record of one custom function including its input/output "
            "definitions and python source — read this before wiring a custom "
            "function block, so the field names match exactly."
        ),
    )
    async def soar_get_custom_function(function_ref: str) -> str:
        """Show one custom function.

        Args:
            function_ref: Custom function id or name fragment.
        """
        record = await app.client.resolve("custom_function", function_ref, label="custom function")
        return to_json(record)

    @mcp.tool(
        title="List source repositories",
        annotations=READ,
        description="List configured source-control repositories (playbook repos).",
    )
    async def soar_list_repos(as_json: bool = False) -> str:
        """List playbook/source repositories.

        Args:
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.get("scm", page_size=100)
        return listing(payload, ["id", "name", "type", "uri", "branch"], as_json=as_json)

    @mcp.tool(
        title="System info",
        annotations=READ,
        description=(
            "Instance version, base URL and configured mode of this MCP server. Call "
            "this first to confirm connectivity and learn what the server may do."
        ),
    )
    async def soar_system_info() -> str:
        """Report instance version and this server's safety configuration."""
        allow = app.settings.label_allowlist
        # Report only *that* a scope exists. Listing the permitted labels would
        # hand over the tenant roster of a multi-tenant instance.
        scope = f"restricted to {len(allow)} label(s)" if allow else "all labels"
        header = details(
            {
                "base_url": app.settings.soar_url,
                "mcp_mode": app.mode.value,
                "label_scope": scope,
                "verify_ssl": app.settings.verify,
            },
            ["base_url", "mcp_mode", "label_scope", "verify_ssl"],
        )
        try:
            info = await app.client.get("system_info")
        except Exception as exc:  # connectivity problems must not hide the config
            return f"{header}\n\nCould not read /rest/system_info: {exc}"
        keys = [k for k in ("version", "base_url", "hostname", "installed_time") if k in info]
        return f"{header}\n\n{details(info, keys) if keys else to_json(info)}"
