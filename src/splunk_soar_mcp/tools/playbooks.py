"""Playbooks: definitions, generated source, and run history."""

from __future__ import annotations

import re

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ..app import SoarApp
from ..errors import SoarError
from ..formatting import details, listing, table, to_json

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)

_DEF = re.compile(r"^def\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)
_DECORATOR = "@phantom.playbook_block()"


def split_blocks(source: str) -> dict[str, str]:
    """Split generated playbook python into ``{function_name: source}``.

    Blocks are top-level ``def``s, each optionally preceded by
    ``@phantom.playbook_block()``. Slicing on the next top-level ``def`` is
    more robust than matching the decorator, which is absent on the helpers
    the editor emits alongside the blocks.
    """
    matches = list(_DEF.finditer(source))
    blocks: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.start()
        # Pull in a preceding decorator line so the block reads as it does in the file.
        prefix = source.rfind("\n", 0, start - 1)
        if prefix != -1 and source[prefix + 1 : start].strip() == _DECORATOR:
            start = prefix + 1
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        blocks[match.group(1)] = source[start:end].rstrip() + "\n"
    return blocks


def register(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.tool(
        title="List playbooks",
        annotations=READ,
        description=(
            "List playbooks, optionally filtered by a name fragment. Shows whether "
            "each is active and what triggers it."
        ),
    )
    async def soar_list_playbooks(
        query: str | None = None,
        label: str | None = None,
        active_only: bool = False,
        page_size: int | None = None,
        as_json: bool = False,
    ) -> str:
        """List playbooks.

        Args:
            query: Case-insensitive name fragment. Omit for all.
            label: Only playbooks scoped to this container label.
            active_only: Only playbooks that are currently active.
            page_size: Rows to return (default 25).
            as_json: Return full JSON records instead of a table.
        """
        extra: dict[str, object] = {}
        if active_only:
            extra["_filter_active"] = "True"
        if label:
            extra["_filter_labels__contains"] = f'"{label}"'
        payload = await app.client.search("playbook", query, page_size=page_size, **extra)
        return listing(
            payload,
            ["id", "name", "scm", "active", "disabled", "playbook_type", "labels"],
            as_json=as_json,
            empty="No playbooks matched.",
        )

    @mcp.tool(
        title="Get playbook",
        annotations=READ,
        description=(
            "Metadata for one playbook: repo, labels, trigger, inputs/outputs and "
            "block count. Use soar_get_playbook_source for the code itself."
        ),
    )
    async def soar_get_playbook(playbook_ref: str) -> str:
        """Show one playbook's metadata.

        Args:
            playbook_ref: Playbook id or name fragment.
        """
        record = await app.client.resolve("playbook", playbook_ref, label="playbook")
        source = record.get("python") or ""
        head = details(
            record,
            [
                "id", "name", "scm", "active", "disabled", "playbook_type", "labels",
                "tags", "description", "create_time", "update_time",
            ],
        )
        blocks = list(split_blocks(source))
        return f"{head}\n\nblocks ({len(blocks)}): {', '.join(blocks) or '(none)'}"

    @mcp.tool(
        title="List playbook blocks",
        annotations=READ,
        description=(
            "List the block/function names inside a playbook's generated python, "
            "with each one's first line. Cheap way to find the block you want "
            "before pulling its source."
        ),
    )
    async def soar_list_playbook_blocks(playbook_ref: str) -> str:
        """List a playbook's blocks.

        Args:
            playbook_ref: Playbook id or name fragment.
        """
        record = await app.client.resolve("playbook", playbook_ref, label="playbook")
        blocks = split_blocks(record.get("python") or "")
        if not blocks:
            return f"Playbook {record.get('name')!r} (id={record.get('id')}) has no python source."
        rows = [
            {"block": name, "lines": src.count("\n"), "signature": src.strip().splitlines()[0]}
            for name, src in blocks.items()
        ]
        return f"playbook {record.get('name')!r} id={record.get('id')}\n\n" + table(
            rows, ["block", "lines", "signature"]
        )

    @mcp.tool(
        title="Get playbook source",
        annotations=READ,
        description=(
            "The generated python for a playbook — the ground truth for block names, "
            "datapaths and custom code. Pass `block` to return just one function "
            "instead of the whole file, which is usually what you want."
        ),
    )
    async def soar_get_playbook_source(playbook_ref: str, block: str | None = None) -> str:
        """Return a playbook's python source.

        Args:
            playbook_ref: Playbook id or name fragment.
            block: Optional block/function name to slice out, e.g. "format_1".
        """
        record = await app.client.resolve("playbook", playbook_ref, label="playbook")
        source = record.get("python") or ""
        if not source:
            return f"Playbook {record.get('name')!r} (id={record.get('id')}) has no python source."
        if not block:
            return source
        blocks = split_blocks(source)
        if block in blocks:
            return blocks[block]
        near = [name for name in blocks if block.lower() in name.lower()]
        if len(near) == 1:
            return blocks[near[0]]
        options = ", ".join(near or blocks)
        return f"No block named {block!r}. Available: {options}"

    @mcp.tool(
        title="List playbook runs",
        annotations=READ,
        description=(
            "Recent playbook executions, newest first. Filter by playbook, container "
            "or status ('success', 'failed', 'running'). The starting point for "
            "'why did this playbook fail'."
        ),
    )
    async def soar_list_playbook_runs(
        playbook_ref: str | None = None,
        container_id: int | None = None,
        status: str | None = None,
        page_size: int | None = None,
        as_json: bool = False,
    ) -> str:
        """List playbook runs.

        Args:
            playbook_ref: Restrict to one playbook (id or name fragment).
            container_id: Restrict to runs on one container.
            status: One of "success", "failed", "running".
            page_size: Rows to return (default 25).
            as_json: Return full JSON records instead of a table.
        """
        extra: dict[str, object] = {}
        if playbook_ref:
            extra["_filter_playbook"] = await app.client.resolve_id(
                "playbook", playbook_ref, label="playbook"
            )
        if container_id is not None:
            extra["_filter_container"] = int(container_id)
        if status:
            extra["_filter_status"] = f'"{status.strip().lower()}"'
        payload = await app.client.search(
            "playbook_run", None, page_size=page_size, sort="id", order="desc", **extra
        )
        return listing(
            payload,
            [
                "id", "playbook_name", "container", "status", "message",
                "start_time", "update_time",
            ],
            as_json=as_json,
            empty="No playbook runs matched.",
        )

    @mcp.tool(
        title="Get playbook run",
        annotations=READ,
        description="Full record of one playbook run, including its result message.",
    )
    async def soar_get_playbook_run(run_id: int) -> str:
        """Show one playbook run.

        Args:
            run_id: The playbook_run id.
        """
        return to_json(await app.client.get(f"playbook_run/{int(run_id)}"))

    @mcp.tool(
        title="Get playbook run log",
        annotations=READ,
        description=(
            "The debug log for one playbook run — every phantom.debug line, block "
            "transition and traceback, in order. This is the fastest way to find "
            "out why a run failed. Use `contains` to grep large logs."
        ),
    )
    async def soar_get_playbook_run_log(
        run_id: int, contains: str | None = None, limit: int = 300
    ) -> str:
        """Return a playbook run's log.

        Args:
            run_id: The playbook_run id.
            contains: Case-insensitive substring filter over log messages.
            limit: Maximum log lines to return (default 300, newest kept).
        """
        run_id = int(run_id)
        # page_size=0 means "every row" here, which is what a log is for.
        payload = await app.client.get(f"playbook_run/{run_id}/log", page_size=0)

        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not rows:
            # A run that is still executing has not written its log yet.
            status = ""
            try:
                record = await app.client.get(f"playbook_run/{run_id}")
                status = f" (status: {record.get('status')})"
            except SoarError:
                pass
            return f"Run {run_id} has no log entries{status}."
        if contains:
            needle = contains.lower()
            rows = [r for r in rows if needle in str(r.get("message", "")).lower()]
            if not rows:
                return f"No log lines in run {run_id} contain {contains!r}."
        clipped = rows[-int(limit) :]

        lines = []
        for entry in clipped:
            stamp = str(entry.get("time") or entry.get("create_time") or "")[:19]
            level = str(entry.get("message_type") or entry.get("severity") or "").lower()
            lines.append(f"[{stamp}] {level:<7} {entry.get('message')}")
        header = f"run {run_id} — {len(clipped)} of {len(rows)} line(s)"
        return f"{header}\n" + "\n".join(lines)

    @mcp.tool(
        title="List action runs",
        annotations=READ,
        description=(
            "App action executions — what was run, whether it succeeded, and the "
            "result message. Includes actions that failed before reaching an app, "
            "which the per-asset execution records do not show."
        ),
    )
    async def soar_list_action_runs(
        container_id: int | None = None,
        status: str | None = None,
        page_size: int | None = None,
        as_json: bool = False,
    ) -> str:
        """List app action runs.

        Args:
            container_id: Restrict to one container.
            status: One of "success", "failed", "running".
            page_size: Rows to return (default 25).
            as_json: Return full JSON records instead of a table.
        """
        extra: dict[str, object] = {}
        if container_id is not None:
            extra["_filter_container"] = int(container_id)
        if status:
            extra["_filter_status"] = f'"{status.strip().lower()}"'
        payload = await app.client.search(
            "action_run", None, page_size=page_size, sort="id", order="desc", **extra
        )
        return listing(
            payload,
            ["id", "action", "status", "message", "container", "playbook_run", "create_time"],
            as_json=as_json,
            empty="No action runs matched.",
        )

    @mcp.tool(
        title="Get action run result",
        annotations=READ,
        description=(
            "One action run in full, together with the per-asset executions beneath "
            "it. Those carry result_data — the actual shape of the data a downstream "
            "datapath would read."
        ),
    )
    async def soar_get_action_run(run_id: int) -> str:
        """Show one app action run.

        Args:
            run_id: The action_run id, as listed by soar_list_action_runs.
        """
        run_id = int(run_id)
        record = await app.client.get(f"action_run/{run_id}")
        # The action_run holds status and message; the per-asset app_runs beneath
        # it hold result_data, which is the shape a datapath actually reads.
        app_runs = (
            await app.client.get("app_run", page_size=25, _filter_action_run=run_id)
        ).get("data") or []
        return to_json({"action_run": record, "app_runs": app_runs})
