"""Encode and decode Splunk SOAR visual-editor clipboard payloads.

The playbook editor's copy/paste format is ``base64(json)`` of a ``coa_data``
envelope holding one or more nodes. Pasting such a payload into the editor
recreates the blocks with every setting filled in, which makes it a practical
way to hand a fully-configured block to someone working in the UI.

The node shapes here were taken from real clipboard payloads copied out of the
editor rather than from documentation, which is why several fields that look
redundant are still written: the editor flags a node as invalid if they are
missing.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

PLATFORM_VERSION = "7.1.0.225"
COA_SCHEMA_VERSION = "5.0.23"

#: Every action, utility and playbook node carries a loop stanza even when
#: looping is off. Omitting it makes the editor flag the node.
LOOP_OFF: dict[str, Any] = {
    "enabled": False,
    "pauseUnit": "m",
    "conditions": [
        {
            "type": "if",
            "logic": "and",
            "comparisons": [
                {"op": "==", "param": "", "value": "", "comparisonKey": "comparison_key_0"}
            ],
            "conditionKey": "condition_key_0",
            "conditionIndex": 0,
        }
    ],
    "pauseValue": 2,
    "exitAfterUnit": "m",
    "exitLoopAfter": 2,
    "exitAfterValue": 10,
    "exitConditionEnabled": False,
}


def encode(obj: Any) -> str:
    return base64.b64encode(json.dumps(obj).encode()).decode()


def decode(payload: str) -> Any:
    return json.loads(base64.b64decode(payload.strip()))


def envelope(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]] | None = None,
    playbook_type: str = "automation",
) -> dict[str, Any]:
    """Wrap built nodes in the clipboard envelope."""
    return {
        "coa_data": {
            "edges": list(edges or []),
            "nodes": {node["id"]: node for node in nodes},
            "platform_version": PLATFORM_VERSION,
            "coa_schema_version": COA_SCHEMA_VERSION,
            "playbook_type": playbook_type,
        }
    }


def emit(
    *nodes: Mapping[str, Any],
    edges: Sequence[Mapping[str, Any]] | None = None,
    playbook_type: str = "automation",
) -> str:
    """Build -> envelope -> base64 in one call. The result is what gets pasted."""
    return encode(envelope(list(nodes), edges=edges, playbook_type=playbook_type))


def function_name_for(display_name: str) -> str:
    """The editor derives functionName from the display name: lowercase, spaces to underscores."""
    return display_name.strip().lower().replace(" ", "_")


def _node(node_id: str, node_type: str, x: int, y: int, data: Mapping[str, Any]) -> dict[str, Any]:
    payload = {"id": str(node_id), "type": node_type, **data}
    return {
        "id": str(node_id),
        "type": node_type,
        "x": x,
        "y": y,
        "data": payload,
        "errors": {},
        "warnings": {},
    }


def _advanced(name: str, *, with_name: bool = True) -> dict[str, Any]:
    if not with_name:
        return {"join": []}
    return {"join": [], "customName": name, "customNameId": 0}


def code(
    node_id: str,
    name: str,
    user_code: str,
    function_name: str | None = None,
    inputs: Iterable[str] | None = None,
    outputs: Iterable[str] | None = None,
    x: int = 1220,
    y: int = 724,
) -> dict[str, Any]:
    """A code block.

    Args:
        user_code: The Custom Code body, indented four spaces — it is a function
            body. It is compiled here so a syntax error surfaces now rather than
            in the editor.
        inputs: Datapath strings such as ``container:id``. Calling
            ``phantom.collect2()`` inside the code is more robust than relying on
            the variable names the editor generates.
        outputs: Output names. Assign ``<function_name>__<output>`` inside the
            code — an undeclared output is never saved, and a block reading it
            fails with a JSONDecodeError.

    ``userCode`` sits at node level, not inside ``data``.
    """
    resolved = function_name or function_name_for(name)
    body = user_code if user_code.startswith("\n") else "\n" + user_code
    if not body.endswith("\n"):
        body += "\n"
    compile("def _block(container=None):\n" + body, "<block>", "exec")  # fail fast

    node = _node(
        node_id,
        "code",
        x,
        y,
        {
            "inputParameters": list(inputs or []),
            "outputVariables": list(outputs or []),
            "advanced": _advanced(name),
            "functionId": 1,
            "functionName": resolved,
        },
    )
    node["userCode"] = body
    return node


def action(
    node_id: str,
    name: str,
    action_name: str,
    connector: str,
    connector_id: str,
    function_name: str,
    connector_configs: Sequence[str],
    parameters: Mapping[str, Any],
    required_parameters: Sequence[str] | None = None,
    x: int = 100,
    y: int = 140,
) -> dict[str, Any]:
    """An app action block. ``function_name`` becomes the generated python def name."""
    return _node(
        node_id,
        "action",
        x,
        y,
        {
            "advanced": _advanced(name),
            "loop": LOOP_OFF,
            "tab": "byAction",
            "action": action_name,
            "connector": connector,
            "actionType": "generic",
            "functionId": 1,
            "parameters": dict(parameters),
            "connectorId": connector_id,
            "functionName": function_name,
            "connectorConfigs": list(connector_configs),
            "connectorVersion": "v1",
            "requiredParameters": list(required_parameters or []),
        },
    )


def decision(
    node_id: str,
    name: str,
    function_name: str,
    comparisons: Sequence[Mapping[str, Any]],
    x: int = 180,
    y: int = 600,
    logic: str = "and",
) -> dict[str, Any]:
    """A decision block.

    Args:
        comparisons: ``[{"op": ">", "param": "<datapath>", "value": "0"}, ...]``.
        logic: ``and`` (all comparisons must hold) or ``or`` (any one) — use
            ``or`` for allowlists.

    An explicit ``else`` branch is always appended; the editor expects one.
    Condition and comparison keys only have to be unique, so they are suffixed
    with the node id to keep two pasted decision blocks from colliding.
    """
    conditions = [
        {
            "type": "if",
            "logic": logic,
            "comparisons": [
                dict(comparison, comparisonKey=f"comparison_key_{index}")
                for index, comparison in enumerate(comparisons)
            ],
            "conditionKey": "condition_key_0",
            "conditionIndex": 0,
        },
        {
            "type": "else",
            "logic": "and",
            "comparisons": [
                {
                    "op": "==",
                    "param": "",
                    "value": "",
                    "comparisonKey": f"comparison_key_else_{node_id}",
                }
            ],
            "conditionKey": f"condition_key_else_{node_id}",
            "conditionIndex": 1,
        },
    ]
    return _node(
        node_id,
        "decision",
        x,
        y,
        {
            "advanced": _advanced(name),
            "conditions": conditions,
            "functionId": 1,
            "functionName": function_name,
        },
    )


def custom_function(
    node_id: str,
    name: str,
    function_name: str,
    cf_name: str,
    cf_repo: str,
    fields: Sequence[Mapping[str, Any]],
    values: Mapping[str, Any],
    description: str = "",
    x: int = 0,
    y: int = 776,
) -> dict[str, Any]:
    """A custom-function (utility) block.

    Args:
        fields: Must mirror the function's real inputs — read them off the
            custom function record rather than inventing them.
        values: ``{field_name: datapath-or-literal}``.

    The downstream datapath is
    ``<function_name>:custom_function_result.data.<output>``. The
    ``<function_name>:custom_function:<output>`` form is the *code block* shape
    and fails at run time with a JSONDecodeError from ``get_block_result``.
    """
    return _node(
        node_id,
        "utility",
        x,
        y,
        {
            "advanced": _advanced(name),
            "loop": LOOP_OFF,
            "values": {cf_name: dict(values)},
            "utilities": {
                cf_name: {
                    "name": cf_name,
                    "label": cf_name,
                    "fields": [
                        {
                            "name": field["name"],
                            "label": field["name"],
                            "required": field.get("required", False),
                            "dataTypes": [],
                            "inputType": "item",
                            "renderType": "datapath",
                            "description": field.get("description", ""),
                            "placeholder": field.get("placeholder", ""),
                        }
                        for field in fields
                    ],
                    "description": description,
                }
            },
            "functionId": 1,
            "selectMore": False,
            "utilityType": "custom_function",
            "functionName": function_name,
            "customFunction": {"name": cf_name, "repoName": cf_repo, "draftMode": False},
        },
    )


def format_block(
    node_id: str,
    name: str,
    function_name: str,
    template: str,
    parameters: Sequence[str],
    x: int = 334,
    y: int = 577,
) -> dict[str, Any]:
    """A format block.

    Args:
        template: The message, with positional slots ``{0}``, ``{1}`` matching
            ``parameters`` by index. Literal newlines are fine.
        parameters: Datapath strings.

    There is no ``loop`` stanza on a format node, unlike action, utility and
    playbook nodes. The downstream datapath is ``<function_name>:formatted_data``
    for the whole message; ``formatted_data.*`` instead makes the consumer run
    once per row, which breaks custom functions taking a single ``message``.
    """
    return _node(
        node_id,
        "format",
        x,
        y,
        {
            "advanced": _advanced(name),
            "functionId": 1,
            "functionName": function_name,
            "parameters": list(parameters),
            "template": template,
        },
    )


def playbook(
    node_id: str,
    playbook_name: str,
    function_name: str,
    repo_id: str,
    repo_name: str,
    inputs: Mapping[str, Sequence[str]],
    playbook_type: str = "data",
    synchronous: bool = False,
    x: int = -180,
    y: int = 124,
) -> dict[str, Any]:
    """A child-playbook block.

    Args:
        inputs: ``{"container_id": ["23"], "triage_data": ["<datapath>"]}`` —
            each value is a list of datapaths.
    """
    return _node(
        node_id,
        "playbook",
        x,
        y,
        {
            "advanced": _advanced(playbook_name, with_name=False),
            "loop": LOOP_OFF,
            "functionId": 1,
            "functionName": function_name,
            "playbookName": playbook_name,
            "playbookRepo": repo_id,
            "playbookRepoName": repo_name,
            "playbookType": playbook_type,
            "synchronous": synchronous,
            "inputs": {
                key: {"datapaths": list(value), "deduplicate": False}
                for key, value in inputs.items()
            },
        },
    )


def summarize(payload: str) -> str:
    """Render a decoded clipboard payload as a short human-readable summary."""
    data = decode(payload)
    coa = data.get("coa_data", data)
    nodes = coa.get("nodes") or {}
    lines = [
        f"platform_version : {coa.get('platform_version')}",
        f"schema_version   : {coa.get('coa_schema_version')}",
        f"playbook_type    : {coa.get('playbook_type')}",
        f"nodes            : {len(nodes)}",
        f"edges            : {len(coa.get('edges') or [])}",
        "",
    ]
    for node_id, node in nodes.items():
        inner = node.get("data") or {}
        display = (inner.get("advanced") or {}).get("customName") or inner.get("playbookName") or ""
        lines.append(
            f"  [{node_id}] {node.get('type')}  fn={inner.get('functionName')!r}  name={display!r}"
        )
    return "\n".join(lines)
