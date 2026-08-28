"""Event metadata: statuses, severities, custom fields, CEF fields, workbooks.

These define the vocabulary a playbook works in. Knowing that `severity` accepts
exactly five values on this instance, or that a container carries a custom field
called `sla_resolution_comment`, is what stops a block being written against a
field that does not exist.
"""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ..app import SoarApp
from ..formatting import listing, table, to_json

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)


def register(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.tool(
        title="List container statuses",
        annotations=READ,
        description=(
            "The container statuses configured on this instance — the exact values "
            "soar_update_container will accept. Instances add custom statuses, so "
            "do not assume new/open/closed."
        ),
    )
    async def soar_list_container_statuses(as_json: bool = False) -> str:
        """List configured container statuses.

        Args:
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.get("container_status", page_size=100)
        return listing(
            payload, ["id", "name", "status_type", "is_default", "disabled"], as_json=as_json
        )

    @mcp.tool(
        title="List severities",
        annotations=READ,
        description=(
            "The severities configured on this instance, with their display order "
            "and colour — the exact values a container or artifact will accept."
        ),
    )
    async def soar_list_severities(as_json: bool = False) -> str:
        """List configured severities.

        Args:
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.get("severity", page_size=100)
        return listing(payload, ["id", "name", "color", "is_default", "disabled"], as_json=as_json)

    @mcp.tool(
        title="List custom fields",
        annotations=READ,
        description=(
            "Container custom fields defined on this instance, with their types. "
            "These are the keys inside a container's `data` object — read this "
            "before writing a datapath against one."
        ),
    )
    async def soar_list_custom_fields(
        query: str | None = None, as_json: bool = False
    ) -> str:
        """List container custom fields.

        Args:
            query: Case-insensitive name fragment. Omit for all.
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.get("custom_field")
        rows = payload.get("data") if isinstance(payload, dict) else payload
        rows = rows or []
        if query:
            needle = query.lower()
            rows = [
                r
                for r in rows
                if needle in str(r.get("name", "")).lower()
                or needle in str(r.get("label", "")).lower()
            ]
        if as_json:
            return to_json(rows)
        return table(
            rows,
            ["name", "label", "data_type", "required", "container_type"],
            empty="No custom fields matched.",
        )

    @mcp.tool(
        title="List CEF fields",
        annotations=READ,
        description=(
            "CEF field definitions known to this instance, with the data types each "
            "contains. Use it to pick the right artifact CEF key — `sourceAddress` "
            "rather than an invented `src_ip` — so contains-based routing works."
        ),
    )
    async def soar_list_cef_fields(query: str | None = None, as_json: bool = False) -> str:
        """List CEF field definitions.

        Args:
            query: Case-insensitive name fragment, e.g. "address". Omit for all.
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.search("cef", query, page_size=300)
        return listing(
            payload,
            ["id", "name", "data_type", "contains", "description"],
            as_json=as_json,
            empty="No CEF fields matched.",
        )

    @mcp.tool(
        title="List workbooks",
        annotations=READ,
        description=(
            "Workbook templates — the phase and task checklists analysts work "
            "through on a case."
        ),
    )
    async def soar_list_workbooks(
        query: str | None = None, as_json: bool = False
    ) -> str:
        """List workbook templates.

        Args:
            query: Case-insensitive name fragment. Omit for all.
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.search("workbook_template", query, page_size=100)
        return listing(
            payload,
            ["id", "name", "description", "is_default", "is_note_required"],
            as_json=as_json,
            empty="No workbooks matched.",
        )

    @mcp.tool(
        title="Get workbook",
        annotations=READ,
        description=(
            "One workbook template with its phases and, under each phase, its "
            "tasks in order — the full checklist as an analyst would see it."
        ),
    )
    async def soar_get_workbook(workbook_ref: str, as_json: bool = False) -> str:
        """Show a workbook's phases and tasks.

        Args:
            workbook_ref: Workbook id or name fragment.
            as_json: Return the raw phase and task records instead of an outline.
        """
        record = await app.client.resolve(
            "workbook_template", workbook_ref, label="workbook"
        )
        phases = (
            await app.client.get(
                "workbook_phase_template",
                page_size=200,
                _filter_template=record["id"],
                sort="order",
                order="asc",
            )
        ).get("data") or []
        # Tasks hang off a phase, not off the template, so they have to be
        # fetched by phase id rather than filtered on the workbook directly.
        phase_ids = [phase["id"] for phase in phases if phase.get("id") is not None]
        tasks = []
        if phase_ids:
            tasks = (
                await app.client.get(
                    "workbook_task_template",
                    page_size=500,
                    _filter_phase__in=json.dumps(phase_ids),
                    sort="order",
                    order="asc",
                )
            ).get("data") or []

        if as_json:
            return to_json({"workbook": record, "phases": phases, "tasks": tasks})

        by_phase: dict[object, list[dict]] = {}
        for task in tasks:
            by_phase.setdefault(task.get("phase"), []).append(task)

        lines = [f"workbook {record.get('name')!r} id={record.get('id')}"]
        if record.get("description"):
            lines.append(f"  {record['description']}")
        for phase in phases:
            lines.append(f"\n  phase {phase.get('order')}: {phase.get('name')}")
            for task in by_phase.get(phase.get("id"), []):
                owner = task.get("owner_name") or task.get("role") or ""
                lines.append(
                    f"    - {task.get('name')}" + (f"  [{owner}]" if owner else "")
                )
        if not phases:
            lines.append("  (no phases defined)")
        return "\n".join(lines)
