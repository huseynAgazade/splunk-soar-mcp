"""Server construction and tool registration."""

from __future__ import annotations

import logging

from mcp.server.mcpserver import MCPServer

from . import prompts, resources
from .app import SoarApp
from .config import Mode, Settings, load_settings
from .tools import containers, lists, platform, playbooks, raw, run, vpe

INSTRUCTIONS = """\
Tools for a Splunk SOAR (Phantom) on-prem instance.

Orientation
  Most tools accept either a numeric id or a name fragment; names are matched
  case-insensitively and an exact match wins over a partial one.
  Listings return compact tables. Pass as_json=true when you need every field.

Where things live
  app / asset          an app is the integration, an asset is one configured
                       instance of it. Actions belong to the app.
  playbook             `soar_get_playbook_source` returns the generated python,
                       which is the ground truth for block and function names.
  playbook_run         a single execution. `soar_get_playbook_run_log` is the
                       fastest way to find out why a run failed.
  container / artifact a container is the event or case; artifacts are the
                       observables on it. Notes and comments attach to containers.
  custom list          a `decided_list` in the API — key/value data playbooks read.

Safety
  The server runs in one of three modes and only registers the tools that mode
  permits, so an unavailable tool means the deployment forbids that class of
  operation — say so rather than looking for a workaround.
"""


def build_server(settings: Settings | None = None) -> MCPServer:
    settings = settings or load_settings()
    app = SoarApp(settings)

    # httpx logs every request at INFO. On a stdio server that floods the
    # client's log pane with one line per REST call and hides anything useful.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    mcp = MCPServer(
        name="splunk-soar",
        title="Splunk SOAR",
        version="0.1.0",
        instructions=INSTRUCTIONS,
    )

    # Read tools are always present.
    platform.register(mcp, app)
    playbooks.register(mcp, app)
    containers.register(mcp, app)
    lists.register(mcp, app)
    vpe.register(mcp, app)
    raw.register(mcp, app)
    resources.register(mcp, app)
    prompts.register(mcp, app)

    # Writes and execution are gated on the configured mode.
    if settings.mode.allows(Mode.STANDARD):
        containers.register_writes(mcp, app)
        lists.register_writes(mcp, app)
    if settings.mode.allows(Mode.FULL):
        run.register(mcp, app)
        containers.register_destructive(mcp, app)
        raw.register_writes(mcp, app)

    return mcp
