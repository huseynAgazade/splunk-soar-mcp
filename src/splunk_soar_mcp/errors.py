"""Error types surfaced to the MCP client.

These subclass the SDK's ``ToolError`` deliberately. The SDK treats a
``ToolError`` as a failure the tool anticipated and passes its message back to
the caller, while any other exception is treated as a crash and reported as a
bare "Error executing tool <name>". Every failure modelled here — an
unreachable instance, a name that matches nothing, a label the deployment
forbids — is one the caller can act on, so the message has to survive.
"""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError


class SoarError(ToolError):
    """A call to the SOAR REST API failed."""

    def __init__(self, message: str, *, status: int | None = None, body: str | None = None):
        self.status = status
        self.body = body
        super().__init__(message)


class NotFoundError(SoarError):
    """A named object could not be resolved to an id."""


class PermissionError_(SoarError):
    """The server's safety mode or label allowlist forbids this operation."""
