"""Prompts: reusable workflows a client can offer as slash commands."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from .app import SoarApp


def register(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.prompt(
        title="Debug a failed playbook run",
        description="Work out why a specific playbook run failed, from its log and action results.",
    )
    def debug_playbook_run(run_id: str) -> str:
        """Investigate a failed playbook run.

        Args:
            run_id: The playbook_run id to investigate.
        """
        return f"""\
Playbook run {run_id} needs investigating. Work through it in this order and
report what you find, not what you tried:

1. `soar_get_playbook_run({run_id})` — status, message, container and playbook.
2. `soar_get_playbook_run_log({run_id})` — read the whole log. The last block to
   log before the failure is where to look, not necessarily the one named in the
   error.
3. If a traceback names a block, `soar_get_playbook_source(<playbook>, block=<name>)`
   for just that function.
4. If an app action failed, `soar_list_action_runs(container_id=<container>)` and
   then `soar_get_action_run(<id>)` — the result_data shows the actual shape a
   downstream datapath would have read.
5. Check the datapath forms against the `soar://reference/datapaths` resource. A
   `JSONDecodeError` out of `get_block_result` almost always means an undeclared
   output or the wrong result form for the producing block type.

Give the root cause and the specific change that fixes it. If the evidence does
not settle it, say what is still unknown."""

    @mcp.prompt(
        title="Triage a container",
        description="Summarise a container, its artifacts and what automation has already run on it.",
    )
    def triage_container(container_id: str) -> str:
        """Summarise a container for an analyst.

        Args:
            container_id: The container id to triage.
        """
        return f"""\
Summarise container {container_id} for an analyst picking it up cold:

1. `soar_get_container({container_id})` — what it is, its label, status, severity and owner.
2. `soar_list_artifacts({container_id})` — the observables. Pull the full CEF for
   anything that looks like the pivot point.
3. `soar_list_playbook_runs(container_id={container_id})` — what automation already ran,
   and whether any of it failed.
4. `soar_list_notes({container_id})` and `soar_list_comments({container_id})` — what a
   human has already concluded. Do not repeat it.

Produce: what happened, what the automation established, what is still open, and
the single next action you would take. Be concrete about indicators — quote the
actual addresses, hashes and hostnames rather than describing them."""

    @mcp.prompt(
        title="Design a playbook block",
        description="Work out a correct block for a playbook, then emit it as a paste-able payload.",
    )
    def design_block(goal: str) -> str:
        """Design and emit a playbook block.

        Args:
            goal: What the block should do, in plain language.
        """
        return f"""\
Build a playbook block that does this: {goal}

Ground the design in what the instance actually has, in this order:

1. Prefer an existing custom function over new custom code — check
   `soar_list_custom_functions` first, and read the one you pick with
   `soar_get_custom_function` so the field names match exactly.
2. For an app action, confirm the action's real parameters with
   `soar_get_app_action` and the asset name with `soar_list_assets`.
3. Check every datapath against the `soar://reference/datapaths` resource before
   writing it. The custom-function result form and the code-block result form are
   different and the wrong one fails at run time.
4. Emit the block with the matching `soar_build_*` tool.

Show the block's inputs, outputs and datapaths in plain text before the payload,
so the operator can check the wiring without decoding it."""
