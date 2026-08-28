"""Custom lists — ``decided_list`` in the REST API."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ..app import SoarApp
from ..formatting import listing, table, to_json

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True
)


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
        title="Create custom list",
        annotations=WRITE,
        description=(
            "Create a new custom list with optional initial rows. Every row should "
            "have the same number of cells — playbooks read lists positionally."
        ),
    )
    async def soar_create_custom_list(name: str, rows: list[list[str]] | None = None) -> str:
        """Create a custom list.

        Args:
            name: Name for the new list. Must not already exist.
            rows: Initial contents, as a list of rows. Omit for an empty list.
        """
        result = await app.client.post(
            "decided_list", {"name": name, "content": [list(r) for r in (rows or [])]}
        )
        return (
            f"Custom list {name!r} created with id {result.get('id')} "
            f"and {len(rows or [])} row(s)."
        )

    @mcp.tool(
        title="Update custom list row",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=True,
        ),
        description=(
            "Replace one row of a custom list, leaving every other row untouched. "
            "Row numbers are zero-based and match soar_get_custom_list's `#` column. "
            "Prefer this over replacing the whole list when you mean to change one entry."
        ),
    )
    async def soar_update_custom_list_row(
        list_ref: str, row_index: int, row: list[str]
    ) -> str:
        """Replace a single row.

        Args:
            list_ref: List id or name fragment.
            row_index: Zero-based row number, as shown by soar_get_custom_list.
            row: The replacement cells for that row.
        """
        record = await app.client.resolve("decided_list", list_ref, label="custom list")
        existing = record.get("content") or []
        if not 0 <= int(row_index) < len(existing):
            return (
                f"List {record.get('name')!r} has {len(existing)} row(s); "
                f"row_index {row_index} is out of range."
            )
        await app.client.post(
            f"decided_list/{record['id']}", {"update_rows": {str(int(row_index)): list(row)}}
        )
        return f"Row {row_index} of list {record.get('name')!r} replaced."

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
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=True,
            open_world_hint=True,
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


def register_destructive(mcp: MCPServer, app: SoarApp) -> None:
    """List deletion. Registered only in `full` mode."""

    @mcp.tool(
        title="Delete custom list",
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=True, open_world_hint=True
        ),
        description=(
            "Permanently delete a custom list. Playbooks that read it will start "
            "failing, so check what uses it first. Requires the list's exact name "
            "to confirm."
        ),
    )
    async def soar_delete_custom_list(list_ref: str, confirm_name: str) -> str:
        """Delete a custom list.

        Args:
            list_ref: List id or name fragment.
            confirm_name: The list's exact name, as a guard against deleting the
                wrong one. The call fails if it does not match.
        """
        record = await app.client.resolve("decided_list", list_ref, label="custom list")
        actual = record.get("name") or ""
        if confirm_name.strip() != actual.strip():
            return (
                f"Refusing to delete: list {record['id']} is named {actual!r}, "
                f"but confirm_name was {confirm_name!r}."
            )
        await app.client.delete(f"decided_list/{record['id']}")
        return f"Custom list {actual!r} (id {record['id']}) deleted."
