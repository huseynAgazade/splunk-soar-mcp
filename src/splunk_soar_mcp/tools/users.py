"""Users and roles.

Reads are always available. Role changes are gated to `full` mode: a role is an
authorisation object, so creating or editing one changes who can do what on the
instance. Roles marked `immutable` are the platform's built-ins and are refused
outright.

SOAR's role delete is a *soft* delete — the role is disabled and disappears from
listings, but the record remains fetchable by id and a second delete returns 404.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ..app import SoarApp
from ..errors import PermissionError_
from ..formatting import details, listing, table, to_json

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True
)
DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True
)

#: The permission areas a role grants, as SOAR names them.
PERMISSION_AREAS = (
    "apps", "assets", "automation_broker", "case_management", "containers",
    "custom_lists", "onprem_automation", "playbooks", "system_settings",
    "users_roles", "workbooks",
)
PERMISSION_VERBS = ("view", "edit", "delete", "execute")


def _permission_table(permissions: Any) -> str:
    if not isinstance(permissions, list) or not permissions:
        return "(no permissions recorded)"
    rows = [
        {
            "area": entry.get("name"),
            **{verb: entry.get(verb, "-") for verb in PERMISSION_VERBS},
        }
        for entry in permissions
        if isinstance(entry, dict)
    ]
    return table(rows, ["area", *PERMISSION_VERBS])


async def _immutable_guard(app: SoarApp, role_id: int) -> dict[str, Any]:
    record = await app.client.get(f"role/{int(role_id)}")
    if record.get("immutable"):
        raise PermissionError_(
            f"Role {record.get('name')!r} is a platform built-in and cannot be "
            f"changed or removed."
        )
    return record


def register(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.tool(
        title="List users",
        annotations=READ,
        description=(
            "Platform users with their type and roles. Useful for resolving the "
            "owner of a container, or checking who holds a role."
        ),
    )
    async def soar_list_users(
        query: str | None = None, page_size: int | None = None, as_json: bool = False
    ) -> str:
        """List users.

        Args:
            query: Case-insensitive username fragment. Omit for all.
            page_size: Rows to return (default 25).
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.search(
            "ph_user", query, field="username", page_size=page_size
        )
        return listing(
            payload,
            ["id", "username", "first_name", "last_name", "email", "type", "is_active"],
            as_json=as_json,
            empty="No users matched.",
        )

    @mcp.tool(
        title="Get user",
        annotations=READ,
        description="One user in full, including their roles and login state.",
    )
    async def soar_get_user(user_ref: str) -> str:
        """Show one user.

        Args:
            user_ref: User id or username fragment.
        """
        return to_json(
            await app.client.resolve("ph_user", user_ref, field="username", label="user")
        )

    @mcp.tool(
        title="List roles",
        annotations=READ,
        description=(
            "Roles defined on the instance. `immutable` marks a platform built-in "
            "that cannot be edited or deleted."
        ),
    )
    async def soar_list_roles(
        query: str | None = None, as_json: bool = False
    ) -> str:
        """List roles.

        Args:
            query: Case-insensitive name fragment. Omit for all.
            as_json: Return full JSON records instead of a table.
        """
        payload = await app.client.search("role", query, page_size=200)
        return listing(
            payload,
            ["id", "name", "type", "immutable", "disabled", "description"],
            as_json=as_json,
            empty="No roles matched.",
        )

    @mcp.tool(
        title="Get role",
        annotations=READ,
        description=(
            "One role with its full permission matrix — for each area (containers, "
            "playbooks, system_settings, users_roles, ...) whether view, edit, "
            "delete and execute are allowed or denied."
        ),
    )
    async def soar_get_role(role_ref: str, as_json: bool = False) -> str:
        """Show a role and its permissions.

        Args:
            role_ref: Role id or name fragment.
            as_json: Return the raw record instead of a rendered matrix.
        """
        record = await app.client.resolve("role", role_ref, label="role")
        if as_json:
            return to_json(record)
        head = details(record, ["id", "name", "type", "immutable", "disabled", "description"])
        return f"{head}\n\npermissions:\n{_permission_table(record.get('permissions'))}"


def register_writes(mcp: MCPServer, app: SoarApp) -> None:
    """Role management. Registered only in `full` mode."""

    @mcp.tool(
        title="Create role",
        annotations=WRITE,
        description=(
            "Create a role. Permissions are given per area as a dict, e.g. "
            '{"containers": {"view": "allow", "edit": "allow"}}. Areas: '
            + ", ".join(PERMISSION_AREAS)
            + ". Verbs: view, edit, delete, execute. Anything unspecified is denied."
        ),
    )
    async def soar_create_role(
        name: str,
        description: str = "",
        permissions: dict[str, dict[str, str]] | None = None,
    ) -> str:
        """Create a role.

        Args:
            name: Role name.
            description: What the role is for.
            permissions: {area: {verb: "allow"|"deny"}}. Omitted areas are denied.
        """
        payload: dict[str, Any] = {"name": name, "description": description}
        if permissions:
            unknown = set(permissions) - set(PERMISSION_AREAS)
            if unknown:
                return (
                    f"Unknown permission area(s): {', '.join(sorted(unknown))}. "
                    f"Valid areas: {', '.join(PERMISSION_AREAS)}"
                )
            payload["permissions"] = [
                {"name": area, **{verb: verbs.get(verb, "deny") for verb in PERMISSION_VERBS}}
                for area, verbs in permissions.items()
            ]
        result = await app.client.post("role", payload)
        return f"Role {name!r} created with id {result.get('id')}."

    @mcp.tool(
        title="Update role",
        annotations=WRITE,
        description=(
            "Change a role's name, description or permissions. Only what you pass "
            "is changed. Platform built-in roles are refused."
        ),
    )
    async def soar_update_role(
        role_ref: str,
        name: str | None = None,
        description: str | None = None,
        permissions: dict[str, dict[str, str]] | None = None,
    ) -> str:
        """Update a role.

        Args:
            role_ref: Role id or name fragment.
            name: New name.
            description: New description.
            permissions: {area: {verb: "allow"|"deny"}} to replace the matrix.
        """
        role_id = await app.client.resolve_id("role", role_ref, label="role")
        record = await _immutable_guard(app, role_id)

        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if permissions:
            unknown = set(permissions) - set(PERMISSION_AREAS)
            if unknown:
                return (
                    f"Unknown permission area(s): {', '.join(sorted(unknown))}. "
                    f"Valid areas: {', '.join(PERMISSION_AREAS)}"
                )
            payload["permissions"] = [
                {"name": area, **{verb: verbs.get(verb, "deny") for verb in PERMISSION_VERBS}}
                for area, verbs in permissions.items()
            ]
        if not payload:
            return "Nothing to update — pass at least one field."
        await app.client.post(f"role/{role_id}", payload)
        return f"Role {record.get('name')!r} (id {role_id}) updated: {', '.join(payload)}."

    @mcp.tool(
        title="Delete role",
        annotations=DESTRUCTIVE,
        description=(
            "Delete a role. SOAR performs a soft delete: the role is disabled and "
            "leaves the listing, but stays fetchable by id, and deleting it again "
            "returns 404. Requires the role's exact name to confirm. Platform "
            "built-ins are refused."
        ),
    )
    async def soar_delete_role(role_ref: str, confirm_name: str) -> str:
        """Delete a role.

        Args:
            role_ref: Role id or name fragment.
            confirm_name: The role's exact name, as a guard against removing the
                wrong one. The call fails if it does not match.
        """
        role_id = await app.client.resolve_id("role", role_ref, label="role")
        record = await _immutable_guard(app, role_id)
        actual = record.get("name") or ""
        if confirm_name.strip() != actual.strip():
            return (
                f"Refusing to delete: role {role_id} is named {actual!r}, but "
                f"confirm_name was {confirm_name!r}."
            )
        await app.client.delete(f"role/{role_id}")
        return (
            f"Role {actual!r} (id {role_id}) deleted. SOAR soft-deletes roles, so it "
            f"is now disabled and out of the listing rather than erased."
        )
