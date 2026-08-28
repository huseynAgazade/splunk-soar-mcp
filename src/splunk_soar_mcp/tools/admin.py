"""Instance administration: settings, licence, health and ingestion.

Everything here is read-only. The administration surface is where an instance's
credentials and tenant arrangements live, so this module deliberately offers no
way to change any of it — a misconfigured SMTP relay or authentication setting
is not something an assistant should be able to do by accident.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ..app import SoarApp
from ..formatting import details, listing, table, to_json

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)

#: Which `system_settings` section backs which page of the admin UI. Kept here
#: because the section names do not obviously match the page titles.
SECTION_GUIDE = """\
company_info_settings      Company Settings > Info
company_roi_settings       Company Settings > ROI
auth_settings              Administration > Authentication
account_security_settings  User Management > Account Security
cred_mgmt_settings         Administration > Credential Management
email_settings             Administration > Email
forwarder_settings         Administration > Forwarders
decided_runner_settings    Administration > Playbook Execution
debug_settings             System Health > Debug
audit_trail_settings       System Health > Audit Trail (what is recorded)
automation_broker          Administration > Automation Broker
response_settings          Response / SLA configuration
clustering, fips, multi_tenant, cloud, privileged, indicators,
telemetry, login_banner, refresh_intervals, search_settings,
severity_inheritance, clickable_urls, multi_condition, whitelist,
generate_playbook_run_report, google_maps_settings, exposed_commands,
resource_scoring, pendo, rum
"""


def register(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.tool(
        title="Get system settings",
        annotations=READ,
        description=(
            "Instance-wide configuration. Call with no arguments to list the "
            "available sections, or pass `section` for one of them. This is where "
            "the Administration and Company Settings pages of the UI get their "
            "data. Credential fields are redacted."
        ),
    )
    async def soar_get_system_settings(section: str | None = None) -> str:
        """Read instance settings.

        Args:
            section: One section, e.g. "email_settings" or "company_info_settings".
                Omit to list every available section with a guide to which UI page
                each one backs.
        """
        settings = await app.client.get("system_settings")
        if not section:
            names = "\n".join(f"  {name}" for name in sorted(settings))
            return (
                f"{len(settings)} section(s). Pass one as `section`.\n\n{names}\n\n"
                f"Which section backs which admin page:\n{SECTION_GUIDE}"
            )
        wanted = section.strip()
        if wanted not in settings:
            near = [name for name in settings if wanted.lower() in name.lower()]
            if len(near) == 1:
                wanted = near[0]
            else:
                options = ", ".join(sorted(near or settings))
                return f"No section named {section!r}. Available: {options}"
        return f"{wanted}:\n{to_json(settings[wanted])}"

    @mcp.tool(
        title="Get licence",
        annotations=READ,
        description=(
            "Licence status, entitlements and current usage — what the instance is "
            "licensed for and how much of it is being consumed."
        ),
    )
    async def soar_get_license() -> str:
        """Read licence information and current usage."""
        return to_json(await app.client.get("license"))

    @mcp.tool(
        title="Get system health",
        annotations=READ,
        description=(
            "Platform health: which services are running, plus load, memory, swap, "
            "database and vault utilisation. The first thing to check when the "
            "instance is behaving oddly rather than a playbook being wrong."
        ),
    )
    async def soar_get_system_health(as_json: bool = False) -> str:
        """Report service and resource health.

        Args:
            as_json: Return the complete record instead of a summary.
        """
        health = await app.client.get("health")
        if as_json:
            return to_json(health)

        services = health.get("services") or []
        rows = services if isinstance(services, list) else [
            {"name": k, **(v if isinstance(v, dict) else {"status": v})}
            for k, v in services.items()
        ]
        head = details(
            health, ["name", "status", "all_running", "guid", "last_snapshot_time"]
        )
        body = table(rows, ["name", "status"], empty="(no service detail reported)")
        extra = {
            key: health[key]
            for key in ("load_data", "memory_data", "swap_data", "db_data", "vault_data")
            if key in health
        }
        return f"{head}\n\nservices:\n{body}\n\nresources:\n{to_json(extra)}"

    @mcp.tool(
        title="List cluster nodes",
        annotations=READ,
        description="Cluster members and their state. Empty on a single-node instance.",
    )
    async def soar_list_cluster_nodes(as_json: bool = False) -> str:
        """List cluster nodes.

        Args:
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.get("cluster_node", page_size=100)
        return listing(
            payload,
            ["id", "name", "status", "ip_address", "last_seen"],
            as_json=as_json,
            empty="Not clustered — no cluster nodes.",
        )

    @mcp.tool(
        title="List feature flags",
        annotations=READ,
        description=(
            "Platform feature flags and whether each is enabled. Useful when a UI "
            "capability is missing and you need to know whether it is switched off."
        ),
    )
    async def soar_list_feature_flags(
        query: str | None = None, as_json: bool = False
    ) -> str:
        """List feature flags.

        Args:
            query: Case-insensitive name fragment. Omit for all.
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.get("feature_flag", page_size=300)
        rows = payload.get("data") or []
        if query:
            needle = query.lower()
            rows = [r for r in rows if needle in str(r.get("name", "")).lower()]
        if as_json:
            return to_json(rows)
        return table(rows, ["id", "name", "value", "description"], empty="No flags matched.")

    @mcp.tool(
        title="List ingestion status",
        annotations=READ,
        description=(
            "Recent ingestion runs per asset — when each poll started and finished. "
            "Use this to find an on-poll integration that has stopped bringing data in."
        ),
    )
    async def soar_list_ingestion_status(
        asset_id: int | None = None, page_size: int | None = None, as_json: bool = False
    ) -> str:
        """List ingestion runs, newest first.

        Args:
            asset_id: Restrict to one asset.
            page_size: Rows to return (default 25).
            asset_id: Restrict to one asset.
            as_json: Return full JSON records instead of a table.
        """
        extra: dict[str, object] = {}
        if asset_id is not None:
            extra["_filter_asset"] = int(asset_id)
        payload = await app.client.search(
            "ingestion_status", None, page_size=page_size, sort="id", order="desc", **extra
        )
        return listing(
            payload,
            ["id", "asset", "start_time", "end_time", "update_time"],
            as_json=as_json,
            empty="No ingestion runs recorded.",
        )
