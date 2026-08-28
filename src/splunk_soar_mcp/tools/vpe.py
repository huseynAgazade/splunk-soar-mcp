"""Visual-editor block tools — build and inspect paste-able clipboard payloads.

These run entirely locally; none of them touch the SOAR instance.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ..app import SoarApp
from ..formatting import to_json
from ..vpe import blocks as B

LOCAL = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

_PASTE = (
    "Returns a base64 payload. The operator pastes it straight into the playbook "
    "editor canvas (click the canvas, then paste) and the block appears fully "
    "configured."
)


def register(mcp: MCPServer, app: SoarApp) -> None:
    @mcp.tool(
        title="Decode VPE block",
        annotations=LOCAL,
        description=(
            "Decode a base64 block payload copied out of the playbook editor. Use "
            "this to learn the exact node shape of a working block before building "
            "a similar one — the editor is the authority on that shape, not docs."
        ),
    )
    async def soar_decode_vpe_block(payload: str, summary_only: bool = True) -> str:
        """Decode a clipboard payload.

        Args:
            payload: The base64 string copied from the playbook editor.
            summary_only: True for a short node listing, False for the full JSON.
        """
        try:
            return B.summarize(payload) if summary_only else to_json(B.decode(payload))
        except Exception as exc:
            return f"Could not decode payload: {exc}"

    @mcp.tool(
        title="Encode VPE block",
        annotations=LOCAL,
        description=(
            "Encode a raw coa_data envelope (or a bare list of nodes) into the "
            "base64 payload the playbook editor accepts."
        ),
    )
    async def soar_encode_vpe_block(envelope: dict[str, Any] | list[dict[str, Any]]) -> str:
        """Encode nodes into a clipboard payload.

        Args:
            envelope: Either a full {"coa_data": {...}} envelope or a list of node dicts.
        """
        if isinstance(envelope, list):
            return B.emit(*envelope)
        if "coa_data" not in envelope:
            return B.emit(envelope)
        return B.encode(envelope)

    @mcp.tool(
        title="Build code block",
        annotations=LOCAL,
        description=(
            "Build a Custom Code block. The code is compiled first, so a syntax "
            "error is reported here rather than failing in the editor. Every output "
            "must be declared: assign `<function_name>__<output>` inside the code, "
            "or downstream blocks fail with a JSONDecodeError. " + _PASTE
        ),
    )
    async def soar_build_code_block(
        name: str,
        user_code: str,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        node_id: str = "9",
        function_name: str | None = None,
    ) -> str:
        """Build a code block.

        Args:
            name: Display name shown on the block, e.g. "Build Digest".
            user_code: The block body, indented four spaces.
            inputs: Datapaths the block consumes, e.g. ["container:id"].
            outputs: Output variable names the block produces.
            node_id: Node id; only matters when pasting several blocks together.
            function_name: Overrides the name derived from `name`.
        """
        try:
            node = B.code(
                node_id, name, user_code,
                function_name=function_name, inputs=inputs, outputs=outputs,
            )
        except SyntaxError as exc:
            return f"user_code does not compile — line {exc.lineno}: {exc.msg}"
        return B.emit(node)

    @mcp.tool(
        title="Build action block",
        annotations=LOCAL,
        description=(
            "Build an app action block. Read the action's real parameters with "
            "soar_get_app_action and the asset name with soar_list_assets first, "
            "so the block is valid on paste. " + _PASTE
        ),
    )
    async def soar_build_action_block(
        name: str,
        action_name: str,
        connector: str,
        connector_id: str,
        connector_configs: list[str],
        parameters: dict[str, Any],
        required_parameters: list[str] | None = None,
        function_name: str | None = None,
        node_id: str = "1",
    ) -> str:
        """Build an action block.

        Args:
            name: Display name of the block.
            action_name: Action as the app exposes it, e.g. "block ip".
            connector: App name, e.g. "CrowdStrike OAuth API".
            connector_id: The app's id.
            connector_configs: Asset names to run against.
            parameters: Action parameters keyed by parameter name.
            required_parameters: Parameter names the action requires.
            function_name: Generated python def name. Derived from `name` if omitted.
            node_id: Node id.
        """
        node = B.action(
            node_id, name, action_name, connector, connector_id,
            function_name or B.function_name_for(name),
            connector_configs, parameters, required_parameters,
        )
        return B.emit(node)

    @mcp.tool(
        title="Build decision block",
        annotations=LOCAL,
        description=(
            "Build a decision block. Comparisons are "
            '[{"op": "==", "param": "<datapath>", "value": "x"}]. An else branch is '
            "added automatically. Use logic='or' for allowlist-style checks. " + _PASTE
        ),
    )
    async def soar_build_decision_block(
        name: str,
        comparisons: list[dict[str, Any]],
        logic: str = "and",
        function_name: str | None = None,
        node_id: str = "2",
    ) -> str:
        """Build a decision block.

        Args:
            name: Display name of the block.
            comparisons: List of {"op", "param", "value"} dicts.
            logic: "and" (all must hold) or "or" (any one).
            function_name: Generated python def name. Derived from `name` if omitted.
            node_id: Node id.
        """
        node = B.decision(
            node_id, name, function_name or B.function_name_for(name), comparisons, logic=logic
        )
        return B.emit(node)

    @mcp.tool(
        title="Build format block",
        annotations=LOCAL,
        description=(
            "Build a format block. The template uses positional slots {0}, {1} that "
            "match `parameters` by index. Downstream, read the result as "
            "`<function_name>:formatted_data` — the `.formatted_data.*` form fans "
            "out one run per row instead. " + _PASTE
        ),
    )
    async def soar_build_format_block(
        name: str,
        template: str,
        parameters: list[str],
        function_name: str | None = None,
        node_id: str = "3",
    ) -> str:
        """Build a format block.

        Args:
            name: Display name of the block.
            template: Message text with {0}, {1} placeholders.
            parameters: Datapaths filling those placeholders, in order.
            function_name: Generated python def name. Derived from `name` if omitted.
            node_id: Node id.
        """
        node = B.format_block(
            node_id, name, function_name or B.function_name_for(name), template, parameters
        )
        return B.emit(node)

    @mcp.tool(
        title="Build custom function block",
        annotations=LOCAL,
        description=(
            "Build a custom-function (utility) block. `fields` must mirror the "
            "function's real inputs — read them with soar_get_custom_function. "
            "Downstream, read results as "
            "`<function_name>:custom_function_result.data.<output>`. " + _PASTE
        ),
    )
    async def soar_build_custom_function_block(
        name: str,
        cf_name: str,
        cf_repo: str,
        fields: list[dict[str, Any]],
        values: dict[str, Any],
        description: str = "",
        function_name: str | None = None,
        node_id: str = "4",
    ) -> str:
        """Build a custom function block.

        Args:
            name: Display name of the block.
            cf_name: The custom function's name.
            cf_repo: The repository the custom function lives in.
            fields: [{"name", "description", "placeholder", "required"}] per input.
            values: {field_name: datapath-or-literal}.
            description: The function's own description, as stored on its record.
            function_name: Generated python def name. Derived from `name` if omitted.
            node_id: Node id.
        """
        node = B.custom_function(
            node_id, name, function_name or B.function_name_for(name),
            cf_name, cf_repo, fields, values, description,
        )
        return B.emit(node)

    @mcp.tool(
        title="Build child playbook block",
        annotations=LOCAL,
        description=(
            "Build a child-playbook block. Each input maps a name to a list of "
            "datapaths. Set synchronous=true when the parent must wait for the "
            "child's outputs. " + _PASTE
        ),
    )
    async def soar_build_playbook_block(
        playbook_name: str,
        repo_id: str,
        repo_name: str,
        inputs: dict[str, list[str]],
        playbook_type: str = "data",
        synchronous: bool = False,
        function_name: str | None = None,
        node_id: str = "5",
    ) -> str:
        """Build a child playbook block.

        Args:
            playbook_name: Name of the child playbook to call.
            repo_id: Id of the repository holding it.
            repo_name: Name of that repository.
            inputs: {input_name: [datapath, ...]}.
            playbook_type: "data" or "automation".
            synchronous: Whether the parent waits for the child to finish.
            function_name: Generated python def name. Derived from the playbook name.
            node_id: Node id.
        """
        node = B.playbook(
            node_id, playbook_name, function_name or B.function_name_for(playbook_name),
            repo_id, repo_name, inputs, playbook_type, synchronous,
        )
        return B.emit(node)
