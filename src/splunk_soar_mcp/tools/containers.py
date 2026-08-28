"""Containers, artifacts, notes and comments — the investigation surface."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ..app import SoarApp
from ..errors import SoarError
from ..formatting import details, listing, to_json

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True
)
DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True
)

CONTAINER_FIELDS = [
    "id", "name", "label", "status", "severity", "sensitivity", "owner_name",
    "tenant", "artifact_count", "create_time", "due_time", "close_time",
    "container_type", "description",
]


def register(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.tool(
        title="List containers",
        annotations=READ,
        description=(
            "List containers (events/cases), newest first. Filter by name fragment, "
            "label, status, severity or owner. On a multi-tenant instance the label "
            "is what scopes a container to a customer."
        ),
    )
    async def soar_list_containers(
        query: str | None = None,
        label: str | None = None,
        status: str | None = None,
        severity: str | None = None,
        owner: str | None = None,
        page_size: int | None = None,
        page: int = 0,
        as_json: bool = False,
    ) -> str:
        """List containers.

        Args:
            query: Case-insensitive fragment of the container name.
            label: Container label, e.g. "events".
            status: Container status, e.g. "new", "open", "closed".
            severity: "low", "medium", "high" or a custom severity name.
            owner: Owner username.
            page_size: Rows to return (default 25).
            page: Zero-based page number for paging through results.
            as_json: Return full JSON records instead of a table.
        """
        extra: dict[str, Any] = {}
        if label:
            app.require_label(label, what="label")
            extra["_filter_label"] = f'"{label}"'
        else:
            # No label asked for: restrict the listing to what this deployment
            # may see, rather than returning every tenant's containers.
            extra.update(app.label_filter())
        for field, value in (
            ("status", status),
            ("severity", severity),
            ("owner_name", owner),
        ):
            if value:
                extra[f"_filter_{field}"] = f'"{value}"'
        payload = await app.client.search(
            "container", query, page_size=page_size, page=page, sort="id", order="desc", **extra
        )
        return listing(
            payload,
            ["id", "name", "label", "status", "severity", "owner_name", "artifact_count", "create_time"],
            as_json=as_json,
            empty="No containers matched.",
        )

    @mcp.tool(
        title="Get container",
        annotations=READ,
        description="Full detail of one container, including its custom fields.",
    )
    async def soar_get_container(container_id: int, as_json: bool = False) -> str:
        """Show one container.

        Args:
            container_id: The container id.
            as_json: Return the complete JSON record instead of a summary.
        """
        record = await app.guarded_container(container_id)
        if as_json:
            return to_json(record)
        summary = details(record, CONTAINER_FIELDS)
        custom = record.get("data") or {}
        if custom:
            summary += f"\n\ncustom fields:\n{to_json(custom)[:2000]}"
        return summary

    @mcp.tool(
        title="List artifacts",
        annotations=READ,
        description=(
            "Artifacts on a container — the observables a playbook reads through "
            "`artifact:*.cef.*` datapaths. Pass as_json for the full CEF payload."
        ),
    )
    async def soar_list_artifacts(
        container_id: int, page_size: int | None = None, as_json: bool = False
    ) -> str:
        """List a container's artifacts.

        Args:
            container_id: The container id.
            page_size: Rows to return (default 25).
            as_json: Return full JSON records, including all CEF fields.
        """
        await app.guarded_container(container_id)
        payload = await app.client.get(
            f"container/{int(container_id)}/artifacts",
            page_size=app.client.clamp(page_size),
            sort="id",
            order="asc",
        )
        return listing(
            payload,
            ["id", "name", "label", "severity", "type", "source_data_identifier", "create_time"],
            as_json=as_json,
            empty="This container has no artifacts.",
        )

    @mcp.tool(
        title="Get artifact",
        annotations=READ,
        description="Full record of one artifact including every CEF field.",
    )
    async def soar_get_artifact(artifact_id: int) -> str:
        """Show one artifact.

        Args:
            artifact_id: The artifact id.
        """
        record = await app.client.get(f"artifact/{int(artifact_id)}")
        await app.guarded_container(record["container"])
        return to_json(record)

    @mcp.tool(
        title="List container notes",
        annotations=READ,
        description="Notes attached to a container, oldest first.",
    )
    async def soar_list_notes(container_id: int, as_json: bool = False) -> str:
        """List a container's notes.

        Args:
            container_id: The container id.
            as_json: Return full JSON records instead of rendered notes.
        """
        await app.guarded_container(container_id)
        payload = await app.client.get(f"container/{int(container_id)}/notes", page_size=100)
        rows = payload.get("data") or []
        if as_json:
            return to_json(rows)
        if not rows:
            return "This container has no notes."
        chunks = []
        for note in rows:
            stamp = str(note.get("create_time") or "")[:19]
            author = note.get("author_name") or note.get("author") or "?"
            chunks.append(
                f"--- note {note.get('id')} — {note.get('title') or '(untitled)'} "
                f"[{author} {stamp}]\n{note.get('content') or ''}"
            )
        return "\n\n".join(chunks)

    @mcp.tool(
        title="List container comments",
        annotations=READ,
        description="Comments on a container, oldest first.",
    )
    async def soar_list_comments(container_id: int) -> str:
        """List a container's comments.

        Args:
            container_id: The container id.
        """
        await app.guarded_container(container_id)
        payload = await app.client.get(f"container/{int(container_id)}/comments", page_size=100)
        rows = payload.get("data") or []
        if not rows:
            return "This container has no comments."
        return "\n".join(
            f"[{str(c.get('time') or c.get('create_time') or '')[:19]}] "
            f"{c.get('user_name') or c.get('user') or '?'}: {c.get('comment')}"
            for c in rows
        )


def register_writes(mcp: MCPServer, app: SoarApp) -> None:
    """Low-risk mutations. Registered in `standard` mode and above."""

    @mcp.tool(
        title="Add container comment",
        annotations=WRITE,
        description="Add a comment to a container. Comments are the lightweight audit trail on a case.",
    )
    async def soar_add_comment(container_id: int, comment: str) -> str:
        """Add a comment.

        Args:
            container_id: The container id.
            comment: Comment text.
        """
        container_id = int(container_id)
        await app.guarded_container(container_id)
        # Comments go to their own collection. Posting {"comment": ...} to the
        # container, or to container/<id>/comments, returns {"success": true}
        # and silently creates nothing — verified against 7.1.
        result = await app.client.post(
            "container_comment", {"container_id": container_id, "comment": comment}
        )
        return f"Comment {result.get('id')} added to container {container_id}."

    @mcp.tool(
        title="Add container note",
        annotations=WRITE,
        description=(
            "Add a note to a container. Notes carry a title and a body and are the "
            "right place for analysis write-ups, unlike comments."
        ),
    )
    async def soar_add_note(
        container_id: int, title: str, content: str, note_format: str = "markdown"
    ) -> str:
        """Add a note.

        Args:
            container_id: The container id.
            title: Note title.
            content: Note body.
            note_format: "markdown" or "html".
        """
        container_id = int(container_id)
        await app.guarded_container(container_id)
        payload = {
            "container_id": container_id,
            "title": title,
            "content": content,
            "note_type": "general",
            "note_format": note_format,
        }
        try:
            await app.client.post("note", payload)
        except SoarError:
            # Older builds expose notes only beneath their container.
            await app.client.post(f"container/{container_id}/notes", payload)
        return f"Note {title!r} added to container {container_id}."

    @mcp.tool(
        title="Update container",
        annotations=WRITE,
        description=(
            "Change a container's status, severity, sensitivity, owner, name or "
            "description. Only the fields you pass are changed."
        ),
    )
    async def soar_update_container(
        container_id: int,
        status: str | None = None,
        severity: str | None = None,
        sensitivity: str | None = None,
        owner: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> str:
        """Update a container's fields.

        Args:
            container_id: The container id.
            status: e.g. "new", "open", "closed".
            severity: e.g. "low", "medium", "high".
            sensitivity: e.g. "white", "green", "amber", "red".
            owner: Username to assign, or "" to unassign.
            name: New container name.
            description: New description.
        """
        container_id = int(container_id)
        await app.guarded_container(container_id)
        payload = {
            key: value
            for key, value in (
                ("status", status),
                ("severity", severity),
                ("sensitivity", sensitivity),
                ("owner_id", owner),
                ("name", name),
                ("description", description),
            )
            if value is not None
        }
        if not payload:
            return "Nothing to update — pass at least one field."
        await app.client.post(f"container/{container_id}", payload)
        return f"Container {container_id} updated: {', '.join(payload)}."

    @mcp.tool(
        title="Add artifact",
        annotations=WRITE,
        description=(
            "Add an artifact to a container. CEF fields go in `cef` as a dict, e.g. "
            '{"sourceAddress": "1.2.3.4", "fileHash": "..."}. Set '
            "run_automation=true only if you intend active playbooks to fire."
        ),
    )
    async def soar_add_artifact(
        container_id: int,
        name: str,
        cef: dict[str, Any] | None = None,
        label: str = "event",
        severity: str = "medium",
        source_data_identifier: str | None = None,
        artifact_type: str | None = None,
        run_automation: bool = False,
    ) -> str:
        """Create an artifact.

        Args:
            container_id: The container to attach it to.
            name: Artifact name.
            cef: CEF field dictionary.
            label: Artifact label (default "event").
            severity: "low", "medium" or "high".
            source_data_identifier: Dedup key. Defaults to the name.
            artifact_type: Optional artifact type, e.g. "network".
            run_automation: Whether active playbooks should fire on this artifact.
        """
        container_id = int(container_id)
        await app.guarded_container(container_id)
        payload: dict[str, Any] = {
            "container_id": container_id,
            "name": name,
            "label": label,
            "severity": severity,
            "cef": cef or {},
            "source_data_identifier": source_data_identifier or name,
            "run_automation": bool(run_automation),
        }
        if artifact_type:
            payload["type"] = artifact_type
        result = await app.client.post("artifact", payload)
        return f"Artifact created: {to_json(result)}"


def register_destructive(mcp: MCPServer, app: SoarApp) -> None:
    """Deletions. Registered only in `full` mode."""

    @mcp.tool(
        title="Delete artifact",
        annotations=DESTRUCTIVE,
        description="Permanently delete an artifact. Cannot be undone.",
    )
    async def soar_delete_artifact(artifact_id: int) -> str:
        """Delete an artifact.

        Args:
            artifact_id: The artifact id.
        """
        artifact_id = int(artifact_id)
        record = await app.client.get(f"artifact/{artifact_id}")
        await app.guarded_container(record["container"])
        await app.client.delete(f"artifact/{artifact_id}")
        return f"Artifact {artifact_id} deleted."

    @mcp.tool(
        title="Create container",
        annotations=WRITE,
        description=(
            "Create a new container. Set run_automation=true only if you intend "
            "active playbooks to fire on it."
        ),
    )
    async def soar_create_container(
        name: str,
        label: str,
        description: str | None = None,
        severity: str = "medium",
        status: str = "new",
        run_automation: bool = False,
    ) -> str:
        """Create a container.

        Args:
            name: Container name.
            label: Container label — decides which playbooks are in scope.
            description: Optional description.
            severity: "low", "medium" or "high".
            status: Usually "new".
            run_automation: Whether active playbooks should fire.
        """
        app.require_label(label)
        payload = {
            "name": name,
            "label": label,
            "severity": severity,
            "status": status,
            "run_automation": bool(run_automation),
        }
        if description:
            payload["description"] = description
        return f"Container created: {to_json(await app.client.post('container', payload))}"

    @mcp.tool(
        title="Delete container",
        annotations=DESTRUCTIVE,
        description=(
            "Permanently delete a container and everything on it — artifacts, notes, "
            "comments and run history. Cannot be undone."
        ),
    )
    async def soar_delete_container(container_id: int, confirm_name: str) -> str:
        """Delete a container.

        Args:
            container_id: The container id.
            confirm_name: The container's exact name, as a guard against deleting
                the wrong one. The call fails if it does not match.
        """
        container_id = int(container_id)
        record = await app.guarded_container(container_id)
        actual = record.get("name") or ""
        if confirm_name.strip() != actual.strip():
            return (
                f"Refusing to delete: container {container_id} is named {actual!r}, "
                f"but confirm_name was {confirm_name!r}."
            )
        await app.client.delete(f"container/{container_id}")
        return f"Container {container_id} ({actual!r}) deleted."
