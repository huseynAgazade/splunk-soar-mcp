#!/usr/bin/env python3
"""Exercise every tool the server exposes, over a real MCP stdio session.

Runs in phases of increasing risk. Each phase is opt-in beyond the first two,
and the run ends with a coverage matrix showing which of the server's tools were
actually called.

    python scripts/test_all_tools.py                 # local + read-only
    python scripts/test_all_tools.py --write         # + writes, confined to --label
    python scripts/test_all_tools.py --write --full  # + create/delete, self-cleaning
    python scripts/test_all_tools.py --write --full --execute   # + run playbook/action

Writes are confined to --label (default: test_label) and every object this script
creates, it deletes. Nothing touches an existing container unless you pass
--container-id explicitly.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import sys
import time

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class Runner:
    """Calls tools, records what happened, and reports coverage at the end."""

    def __init__(self, session: ClientSession, verbose: bool = False):
        self.session = session
        self.verbose = verbose
        self.results: list[tuple[str, str, str]] = []
        self.available: set[str] = set()

    # -- reporting ---------------------------------------------------------

    def record(self, tool: str, status: str, note: str = "") -> None:
        colour = {PASS: GREEN, FAIL: RED, SKIP: YELLOW}[status]
        print(f"  {colour}{status}{RESET}  {tool:<34} {DIM}{note[:90]}{RESET}")
        self.results.append((tool, status, note))

    def phase(self, title: str) -> None:
        print(f"\n{'=' * 78}\n  {title}\n{'=' * 78}")

    # -- calling -----------------------------------------------------------

    async def call(self, tool: str, args: dict | None = None) -> str | None:
        """Call a tool. Returns its text on success, None on failure."""
        if tool not in self.available:
            self.record(tool, SKIP, "not registered in this mode")
            return None
        try:
            result = await self.session.call_tool(tool, args or {})
        except Exception as exc:
            self.record(tool, FAIL, f"{type(exc).__name__}: {exc}")
            return None

        text = "".join(
            block.text for block in result.content if getattr(block, "type", "") == "text"
        ).strip()
        if result.is_error:
            self.record(tool, FAIL, text)
            return None
        first = text.splitlines()[0] if text else "(empty)"
        self.record(tool, PASS, first)
        if self.verbose and text:
            print(f"{DIM}{chr(10).join('        ' + ln for ln in text.splitlines()[:12])}{RESET}")
        return text

    def summary(self) -> int:
        counts = {PASS: 0, FAIL: 0, SKIP: 0}
        for _, status, _ in self.results:
            counts[status] += 1
        called = {tool for tool, status, _ in self.results if status == PASS}
        untested = sorted(self.available - called)

        print(f"\n{'=' * 78}\n  COVERAGE\n{'=' * 78}")
        print(f"  registered tools : {len(self.available)}")
        print(f"  exercised        : {len(called)}")
        print(f"  {GREEN}pass{RESET} {counts[PASS]}   {RED}fail{RESET} {counts[FAIL]}"
              f"   {YELLOW}skip{RESET} {counts[SKIP]}")
        if untested:
            print(f"\n  not exercised ({len(untested)}):")
            for tool in untested:
                print(f"    - {tool}")

        failures = [(t, n) for t, s, n in self.results if s == FAIL]
        if failures:
            print(f"\n  {RED}FAILURES{RESET}")
            for tool, note in failures:
                print(f"    {tool}\n      {note[:400]}")
        return 1 if counts[FAIL] else 0


def first_id(table: str | None) -> str | None:
    """Pull the first id out of a rendered table."""
    if not table:
        return None
    for line in table.splitlines()[2:]:
        match = re.match(r"\s*(\d+)\s", line)
        if match:
            return match.group(1)
    return None


def first_block_name(table: str | None) -> str | None:
    """First block name out of soar_list_playbook_blocks' table.

    Its first column is a name, not an id, and the row after the header is a
    rule of dashes — both of which the id-based helpers get wrong.
    """
    if not table:
        return None
    for line in table.splitlines():
        candidate = re.split(r"\s{2,}", line.strip())[0]
        if re.fullmatch(r"[A-Za-z_]\w*", candidate) and candidate != "block":
            return candidate
    return None


def first_cell(table: str | None, column: int) -> str | None:
    if not table:
        return None
    for line in table.splitlines()[2:]:
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) > column and parts[0].isdigit():
            return parts[column]
    return None


# --------------------------------------------------------------------------
# phases
# --------------------------------------------------------------------------


async def phase_local(run: Runner) -> None:
    """Block builders and the codec. No network involved."""
    run.phase("PHASE 1 — visual editor blocks (local, no instance needed)")

    code = await run.call("soar_build_code_block", {
        "name": "Smoke Code",
        "user_code": '    smoke_code__message = "hello"\n',
        "inputs": ["container:id"],
        "outputs": ["message"],
    })
    await run.call("soar_decode_vpe_block", {"payload": code or "", "summary_only": True})
    await run.call("soar_decode_vpe_block", {"payload": code or "", "summary_only": False})

    await run.call("soar_build_action_block", {
        "name": "Smoke Action",
        "action_name": "geolocate ip",
        "connector": "MaxMind",
        "connector_id": "1",
        "connector_configs": ["maxmind_asset"],
        "parameters": {"ip": "artifact:*.cef.sourceAddress"},
        "required_parameters": ["ip"],
    })
    await run.call("soar_build_decision_block", {
        "name": "Smoke Decision",
        "comparisons": [{"op": "==", "param": "container:severity", "value": "high"}],
        "logic": "or",
    })
    await run.call("soar_build_format_block", {
        "name": "Smoke Format",
        "template": "container {0} is {1}",
        "parameters": ["container:name", "container:severity"],
    })
    await run.call("soar_build_custom_function_block", {
        "name": "Smoke CF",
        "cf_name": "example_function",
        "cf_repo": "local",
        "fields": [{"name": "message", "description": "text to send"}],
        "values": {"message": "smoke_format:formatted_data"},
    })
    await run.call("soar_build_playbook_block", {
        "playbook_name": "Child Playbook",
        "repo_id": "1",
        "repo_name": "local",
        "inputs": {"container_id": ["container:id"]},
        "synchronous": True,
    })
    await run.call("soar_encode_vpe_block", {
        "envelope": [{"id": "1", "type": "format", "x": 0, "y": 0,
                      "data": {"id": "1", "type": "format", "functionName": "f"},
                      "errors": {}, "warnings": {}}]
    })

    # A syntax error must come back as a message, not a crash.
    bad = await run.call("soar_build_code_block", {"name": "Bad", "user_code": "    if True\n"})
    if bad and "does not compile" not in bad:
        run.record("soar_build_code_block", FAIL, "bad syntax was not reported")


async def phase_read(run: Runner, args) -> dict:
    """Every read tool, chaining real ids discovered as it goes."""
    run.phase("PHASE 2 — reads against the live instance")
    found: dict[str, str | None] = {}

    await run.call("soar_system_info")

    apps = await run.call("soar_list_apps", {"page_size": 5})
    app_id = first_id(apps)
    found["app"] = app_id
    if app_id:
        actions = await run.call("soar_list_app_actions", {"app_ref": app_id})
        action_name = first_cell(actions, 1)
        if action_name:
            await run.call("soar_get_app_action",
                           {"app_ref": app_id, "action_name": action_name})
        else:
            run.record("soar_get_app_action", SKIP, "no action found on the sampled app")
    else:
        run.record("soar_list_app_actions", SKIP, "no app to sample")
        run.record("soar_get_app_action", SKIP, "no app to sample")

    assets = await run.call("soar_list_assets", {"page_size": 5})
    if (asset_id := first_id(assets)):
        found["asset"] = asset_id
        await run.call("soar_get_asset", {"asset_ref": asset_id})
    else:
        run.record("soar_get_asset", SKIP, "no assets on this instance")

    functions = await run.call("soar_list_custom_functions", {"page_size": 5})
    if (fn_id := first_id(functions)):
        await run.call("soar_get_custom_function", {"function_ref": fn_id})
    else:
        run.record("soar_get_custom_function", SKIP, "no custom functions")

    await run.call("soar_list_repos")

    playbooks = await run.call("soar_list_playbooks", {"page_size": 5})
    playbook_id = first_id(playbooks)
    found["playbook"] = playbook_id
    if playbook_id:
        await run.call("soar_get_playbook", {"playbook_ref": playbook_id})
        blocks = await run.call("soar_list_playbook_blocks", {"playbook_ref": playbook_id})
        await run.call("soar_get_playbook_source", {"playbook_ref": playbook_id})
        block_name = first_block_name(blocks)
        if block_name:
            await run.call("soar_get_playbook_source",
                           {"playbook_ref": playbook_id, "block": block_name})
    else:
        for tool in ("soar_get_playbook", "soar_list_playbook_blocks",
                     "soar_get_playbook_source"):
            run.record(tool, SKIP, "no playbooks on this instance")

    # Prefer a finished run: the newest one is often still executing, and a
    # running playbook has not written its log yet.
    runs = await run.call("soar_list_playbook_runs", {"page_size": 5, "status": "success"})
    run_id = first_id(runs)
    if not run_id:
        runs = await run.call("soar_list_playbook_runs", {"page_size": 5})
        run_id = first_id(runs)
    if run_id:
        await run.call("soar_get_playbook_run", {"run_id": int(run_id)})
        await run.call("soar_get_playbook_run_log", {"run_id": int(run_id), "limit": 20})
        await run.call("soar_get_playbook_run_log",
                       {"run_id": int(run_id), "contains": "error", "limit": 20})
    else:
        for tool in ("soar_get_playbook_run", "soar_get_playbook_run_log"):
            run.record(tool, SKIP, "no playbook runs yet")

    action_runs = await run.call("soar_list_action_runs", {"page_size": 5})
    if (action_run_id := first_id(action_runs)):
        await run.call("soar_get_action_run", {"run_id": int(action_run_id)})
    else:
        run.record("soar_get_action_run", SKIP, "no action runs yet")

    containers = await run.call(
        "soar_list_containers",
        {"page_size": 5, **({"label": args.label} if args.label else {})},
    )
    container_id = args.container_id or first_id(containers)
    if not container_id:
        containers = await run.call("soar_list_containers", {"page_size": 5})
        container_id = first_id(containers)
    found["container"] = container_id

    if container_id:
        cid = int(container_id)
        await run.call("soar_get_container", {"container_id": cid})
        artifacts = await run.call("soar_list_artifacts", {"container_id": cid})
        if (artifact_id := first_id(artifacts)):
            await run.call("soar_get_artifact", {"artifact_id": int(artifact_id)})
        else:
            run.record("soar_get_artifact", SKIP, "sampled container has no artifacts")
        await run.call("soar_list_notes", {"container_id": cid})
        await run.call("soar_list_comments", {"container_id": cid})
    else:
        for tool in ("soar_get_container", "soar_list_artifacts", "soar_get_artifact",
                     "soar_list_notes", "soar_list_comments"):
            run.record(tool, SKIP, "no containers on this instance")

    lists = await run.call("soar_list_custom_lists", {"page_size": 5})
    if (list_id := first_id(lists)):
        found["list"] = list_id
        await run.call("soar_get_custom_list", {"list_ref": list_id})
    else:
        run.record("soar_get_custom_list", SKIP, "no custom lists")

    await run.call("soar_rest_get", {"path": "version", "params": {}})
    return found


async def phase_admin(run: Runner) -> None:
    """Administration, metadata, users and roles — all read-only."""
    run.phase("PHASE 2b — administration, metadata, users and roles")

    await run.call("soar_get_system_settings", {})
    await run.call("soar_get_system_settings", {"section": "company_info_settings"})
    await run.call("soar_get_license", {})
    await run.call("soar_get_system_health", {})
    await run.call("soar_list_cluster_nodes", {})
    await run.call("soar_list_feature_flags", {"query": "playbook"})
    await run.call("soar_list_ingestion_status", {"page_size": 3})

    await run.call("soar_list_container_statuses", {})
    await run.call("soar_list_severities", {})
    await run.call("soar_list_custom_fields", {})
    await run.call("soar_list_cef_fields", {"query": "address"})

    workbooks = await run.call("soar_list_workbooks", {"page_size": 5})
    if (workbook_id := first_id(workbooks)):
        await run.call("soar_get_workbook", {"workbook_ref": workbook_id})
    else:
        run.record("soar_get_workbook", SKIP, "no workbook templates defined")

    users = await run.call("soar_list_users", {"page_size": 5})
    if (user_id := first_id(users)):
        await run.call("soar_get_user", {"user_ref": user_id})
    else:
        run.record("soar_get_user", SKIP, "no users returned")

    roles = await run.call("soar_list_roles", {})
    if (role_id := first_id(roles)):
        await run.call("soar_get_role", {"role_ref": role_id})
    else:
        run.record("soar_get_role", SKIP, "no roles returned")


async def phase_admin_writes(run: Runner) -> None:
    """Custom list and role lifecycles, entirely on objects this script creates."""
    run.phase("PHASE 3b — custom list and role lifecycles (throwaway objects)")
    stamp = int(time.time())

    list_name = f"zz_mcp_probe_list_{stamp}"
    created_list = await run.call(
        "soar_create_custom_list", {"name": list_name, "rows": [["a", "1"], ["b", "2"]]}
    )
    if created_list:
        await run.call(
            "soar_update_custom_list_row",
            {"list_ref": list_name, "row_index": 0, "row": ["A", "99"]},
        )
        await run.call("soar_append_to_custom_list", {"list_ref": list_name, "row": ["c", "3"]})
        await run.call("soar_get_custom_list", {"list_ref": list_name})
        await run.call(
            "soar_replace_custom_list", {"list_ref": list_name, "rows": [["only", "row"]]}
        )
        await run.call(
            "soar_delete_custom_list", {"list_ref": list_name, "confirm_name": list_name}
        )
    else:
        for tool in ("soar_update_custom_list_row", "soar_append_to_custom_list",
                     "soar_replace_custom_list", "soar_delete_custom_list"):
            run.record(tool, SKIP, "no throwaway list to work on")

    role_name = f"zz_mcp_probe_role_{stamp}"
    created_role = await run.call(
        "soar_create_role",
        {
            "name": role_name,
            "description": "Created by test_all_tools.py. Safe to delete.",
            "permissions": {"containers": {"view": "allow"}},
        },
    )
    if created_role:
        await run.call("soar_get_role", {"role_ref": role_name})
        await run.call(
            "soar_update_role", {"role_ref": role_name, "description": "edited by the probe"}
        )
        await run.call(
            "soar_delete_role", {"role_ref": role_name, "confirm_name": role_name}
        )
    else:
        for tool in ("soar_update_role", "soar_delete_role"):
            run.record(tool, SKIP, "no throwaway role to work on")


async def phase_write(run: Runner, args, found: dict) -> str | None:
    """Writes, confined to --label. Creates its own container when it can."""
    run.phase(f"PHASE 3 — writes (label={args.label!r})")

    created: str | None = None
    target = args.container_id

    if "soar_create_container" in run.available and not target:
        made = await run.call("soar_create_container", {
            "name": f"mcp-smoke-{int(time.time())}",
            "label": args.label,
            "description": "Created by splunk-soar-mcp test_all_tools.py. Safe to delete.",
            "severity": "low",
            "run_automation": False,
        })
        if made:
            match = re.search(r'"id":\s*(\d+)', made)
            created = target = match.group(1) if match else None

    if not target:
        run.record("(phase 3)", SKIP,
                   "no writable container — pass --container-id or enable --full")
        return None

    cid = int(target)
    print(f"{DIM}        writing to container {cid}{RESET}")

    await run.call("soar_add_comment", {
        "container_id": cid, "comment": "splunk-soar-mcp smoke test comment."
    })
    await run.call("soar_add_note", {
        "container_id": cid,
        "title": "MCP smoke test",
        "content": "Written by `test_all_tools.py`. Safe to delete.",
    })
    await run.call("soar_update_container", {
        "container_id": cid, "severity": "low",
        "description": "Touched by the MCP smoke test.",
    })
    artifact = await run.call("soar_add_artifact", {
        "container_id": cid,
        "name": "mcp-smoke-artifact",
        "cef": {"sourceAddress": "192.0.2.1", "message": "test data"},
        "label": "event", "severity": "low", "run_automation": False,
    })

    # Re-read, to prove the writes landed.
    await run.call("soar_list_notes", {"container_id": cid})
    await run.call("soar_list_comments", {"container_id": cid})

    if args.list_name:
        await run.call("soar_append_to_custom_list",
                       {"list_ref": args.list_name, "row": ["mcp-smoke", "safe to delete"]})
        current = await run.call("soar_get_custom_list",
                                 {"list_ref": args.list_name, "as_json": True})
        if current:
            try:
                rows = [r for r in json.loads(current) if r and r[0] != "mcp-smoke"]
                await run.call("soar_replace_custom_list",
                               {"list_ref": args.list_name, "rows": rows})
            except json.JSONDecodeError:
                run.record("soar_replace_custom_list", SKIP, "could not parse list contents")
    elif "soar_create_custom_list" not in run.available:
        run.record("soar_append_to_custom_list", SKIP, "pass --list-name to test list writes")
        run.record("soar_replace_custom_list", SKIP, "pass --list-name to test list writes")

    if artifact and "soar_delete_artifact" in run.available:
        match = re.search(r'"id":\s*(\d+)', artifact)
        if match:
            await run.call("soar_delete_artifact", {"artifact_id": int(match.group(1))})

    return created


async def phase_execute(run: Runner, args, found: dict, container: str | None) -> None:
    run.phase("PHASE 4 — execution (real automation)")
    target = container or args.container_id
    if not target:
        run.record("soar_run_playbook", SKIP, "no safe container to run against")
        run.record("soar_run_action", SKIP, "no safe container to run against")
        return

    if args.playbook:
        await run.call("soar_run_playbook",
                       {"playbook_ref": args.playbook, "container_id": int(target),
                        "scope": "new"})
    else:
        run.record("soar_run_playbook", SKIP, "pass --playbook to test execution")

    if args.action and args.asset:
        await run.call("soar_run_action", {
            "action": args.action, "asset": args.asset,
            "container_id": int(target), "parameters": args.action_params,
        })
    else:
        run.record("soar_run_action", SKIP, "pass --action and --asset to test execution")


async def phase_raw_writes(run: Runner, container: str | None) -> None:
    run.phase("PHASE 5 — raw REST escape hatches")
    if not container:
        run.record("soar_rest_post", SKIP, "no throwaway container to write to")
        run.record("soar_rest_delete", SKIP, "no throwaway object to delete")
        return
    await run.call("soar_rest_post", {
        "path": f"container/{container}",
        "payload": {"description": "Set via soar_rest_post during the smoke test."},
    })
    run.record("soar_rest_delete", SKIP,
               "exercised by the container cleanup below, not called directly")


async def cleanup(run: Runner, created: str | None) -> None:
    if not created:
        return
    run.phase("CLEANUP")
    name = None
    detail = await run.call("soar_get_container", {"container_id": int(created), "as_json": True})
    if detail:
        with contextlib.suppress(json.JSONDecodeError):
            name = json.loads(detail).get("name")
    if name and "soar_delete_container" in run.available:
        await run.call("soar_delete_container",
                       {"container_id": int(created), "confirm_name": name})
    else:
        print(f"  {YELLOW}NOTE{RESET}  container {created} was left in place — delete it by hand")


# --------------------------------------------------------------------------


async def main(args) -> int:
    env = dict(os.environ)
    if args.mode:
        env["SOAR_MCP_MODE"] = args.mode

    params = StdioServerParameters(
        command=sys.executable, args=["-m", "splunk_soar_mcp"], env=env, cwd=os.getcwd()
    )

    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        info = await session.initialize()
        run = Runner(session, verbose=args.verbose)
        run.available = {tool.name for tool in (await session.list_tools()).tools}

        print(f"connected to {info.server_info.name} {info.server_info.version} — "
              f"{len(run.available)} tools registered")

        await phase_local(run)

        if args.local_only:
            return run.summary()

        found = await phase_read(run, args)
        await phase_admin(run)

        created = None
        if args.write:
            created = await phase_write(run, args, found)
            await phase_admin_writes(run)
            if args.full:
                await phase_raw_writes(run, created)
            if args.execute:
                await phase_execute(run, args, found, created)
            await cleanup(run, created)
        else:
            print(f"\n{YELLOW}writes skipped — pass --write to exercise them{RESET}")

        return run.summary()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--local-only", action="store_true",
                        help="only the block builders; no instance needed")
    parser.add_argument("--write", action="store_true", help="exercise the write tools")
    parser.add_argument("--full", action="store_true",
                        help="run the server in full mode (create/delete/raw POST)")
    parser.add_argument("--execute", action="store_true",
                        help="also run a playbook and an action — real automation")
    parser.add_argument("--mode", choices=("readonly", "standard", "full"),
                        help="override SOAR_MCP_MODE for this run")
    parser.add_argument("--label", default="test_label",
                        help="container label writes are confined to (default: test_label)")
    parser.add_argument("--container-id", help="write to this container instead of creating one")
    parser.add_argument("--list-name", help="custom list to exercise append/replace against")
    parser.add_argument("--playbook", help="playbook to run in --execute")
    parser.add_argument("--action", help="action name to run in --execute")
    parser.add_argument("--asset", help="asset to run --action against")
    parser.add_argument("--action-params", type=json.loads, default={},
                        help="JSON parameters for --action")
    parser.add_argument("-v", "--verbose", action="store_true", help="print tool output")
    parsed = parser.parse_args()
    if parsed.full and not parsed.mode:
        parsed.mode = "full"
    raise SystemExit(asyncio.run(main(parsed)))
