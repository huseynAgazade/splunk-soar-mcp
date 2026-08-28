"""Resources: reference material and a live instance summary."""

from __future__ import annotations

from importlib import resources as importlib_resources

from mcp.server.mcpserver import MCPServer

from .app import SoarApp

_PACKAGE = "splunk_soar_mcp.reference"


def _read(filename: str) -> str:
    try:
        return importlib_resources.files(_PACKAGE).joinpath(filename).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        return f"Reference file {filename!r} is unavailable: {exc}"


def register(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.resource(
        "soar://reference/phantom-api",
        name="phantom.* callable reference",
        description=(
            "Every callable on the `phantom` object inside a running playbook block "
            "or custom function on SOAR 7.1, grouped by purpose. A ground-truth "
            "dump: it proves a name exists, it does not give signatures."
        ),
        mime_type="text/markdown",
    )
    def phantom_api() -> str:
        return _read("phantom_api.md")

    @mcp.resource(
        "soar://reference/datapaths",
        name="Datapath reference",
        description=(
            "How each block type's output is read downstream, which forms fan out, "
            "and why the wrong form fails with a JSONDecodeError."
        ),
        mime_type="text/markdown",
    )
    def datapaths() -> str:
        return _read("datapaths.md")

    @mcp.resource(
        "soar://reference/vpe-blocks",
        name="Visual editor block format",
        description=(
            "The clipboard payload format the playbook editor accepts, the node "
            "types, and the fields the editor rejects a node for omitting."
        ),
        mime_type="text/markdown",
    )
    def vpe_blocks() -> str:
        return _read("vpe_blocks.md")

    @mcp.resource(
        "soar://instance/summary",
        name="Instance summary",
        description="Live counts of apps, assets, playbooks, custom functions and lists.",
        mime_type="text/plain",
    )
    async def instance_summary() -> str:
        lines = [f"instance : {app.settings.soar_url}", f"mcp mode : {app.mode.value}", ""]
        for label, path in (
            ("apps", "app"),
            ("assets", "asset"),
            ("playbooks", "playbook"),
            ("custom functions", "custom_function"),
            ("custom lists", "decided_list"),
            ("containers", "container"),
        ):
            try:
                payload = await app.client.get(path, page_size=1)
                lines.append(f"{label:<18} {payload.get('count', '?')}")
            except Exception as exc:
                lines.append(f"{label:<18} unavailable ({exc})")
        return "\n".join(lines)
