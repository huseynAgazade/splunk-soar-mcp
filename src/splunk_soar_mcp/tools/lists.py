"""Custom lists — ``decided_list`` in the REST API."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ..app import SoarApp
from ..formatting import listing, table, to_json

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False)


def register(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.tool(
        title="List custom lists",
        annotations=READ,
        description="List custom lists (decided lists) — the key/value data playbooks read.",
    )
    async def soar_list_custom_lists(
        query: str | None = None, page_size: int | None = None, as_json: bool = False
    ) -> str:
        """List custom lists.

        Args:
            query: Case-insensitive name fragment. Omit for all.
            page_size: Rows to return (default 25).
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.search("decided_list", query, page_size=page_size)
        return listing(
            payload, ["id", "name", "create_time", "update_time"], as_json=as_json,
            empty="No custom lists matched.",
        )

    @mcp.tool(
        title="Get custom list",
        annotations=READ,
        description="The contents of one custom list, as a numbered grid of rows.",
    )
    async def soar_get_custom_list(list_ref: str, as_json: bool = False) -> str:
        """Show a custom list's contents.

        Args:
            list_ref: List id or name fragment.
            as_json: Return the raw content array instead of a rendered grid.
        """
        record = await app.client.resolve("decided_list", list_ref, label="custom list")
        content = record.get("content") or []
        if as_json:
            return to_json(content)
        if not content:
            return f"List {record.get('name')!r} (id={record.get('id')}) is empty."
        width = max(len(row) for row in content)
        rows = [
            {"#": index, **{f"col{i}": (row[i] if i < len(row) else "") for i in range(width)}}
            for index, row in enumerate(content)
        ]
        header = f"list {record.get('name')!r} id={record.get('id')} — {len(content)} row(s)\n"
        return header + table(rows, ["#"] + [f"col{i}" for i in range(width)])


def register_writes(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.tool(
        title="Append row to custom list",
        annotations=WRITE,
        description=(
            "Append one row to a custom list. Existing rows are untouched — this is "
            "the safe way to add to a suppression or allow list."
        ),
    )
    async def soar_append_to_custom_list(list_ref: str, row: list[str]) -> str:
        """Append a row.

        Args:
            list_ref: List id or name fragment.
            row: The cells of the new row, e.g. ["1.2.3.4", "false positive"].
        """
        record = await app.client.resolve("decided_list", list_ref, label="custom list")
        await app.client.post(f"decided_list/{record['id']}", {"append_rows": [list(row)]})
        return f"Appended 1 row to list {record.get('name')!r} (id={record['id']})."

    @mcp.tool(
        title="Replace custom list contents",
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=True, idempotent_hint=True
        ),
        description=(
            "Replace a custom list's entire contents. Every existing row is "
            "discarded — read the list first, and prefer "
            "soar_append_to_custom_list when you only mean to add."
        ),
    )
    async def soar_replace_custom_list(list_ref: str, rows: list[list[str]]) -> str:
        """Overwrite a custom list.

        Args:
            list_ref: List id or name fragment.
            rows: The complete new contents, as a list of rows.
        """
        record = await app.client.resolve("decided_list", list_ref, label="custom list")
        before = len(record.get("content") or [])
        await app.client.post(f"decided_list/{record['id']}", {"content": [list(r) for r in rows]})
        return (
            f"List {record.get('name')!r} (id={record['id']}) replaced: "
            f"{before} row(s) -> {len(rows)} row(s)."
        )
