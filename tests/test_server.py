import json

import httpx
import pytest
import respx
from conftest import BASE, make_settings

from splunk_soar_mcp.server import build_server

WRITE_TOOLS = {"soar_add_comment", "soar_add_note", "soar_update_container", "soar_add_artifact"}
FULL_TOOLS = {"soar_run_playbook", "soar_run_action", "soar_delete_container", "soar_rest_post"}


async def tool_names(mode: str) -> set[str]:
    server = build_server(make_settings(SOAR_MCP_MODE=mode))
    return {tool.name for tool in await server.list_tools()}


async def test_readonly_registers_no_mutating_tool():
    names = await tool_names("readonly")
    assert not (names & WRITE_TOOLS)
    assert not (names & FULL_TOOLS)
    assert "soar_list_containers" in names


async def test_standard_adds_safe_writes_but_not_execution():
    names = await tool_names("standard")
    assert names >= WRITE_TOOLS
    assert not (names & FULL_TOOLS)


async def test_full_adds_execution_and_deletion():
    assert await tool_names("full") >= FULL_TOOLS


async def test_modes_are_strictly_nested():
    readonly, standard, full = (
        await tool_names("readonly"),
        await tool_names("standard"),
        await tool_names("full"),
    )
    assert readonly < standard < full


async def test_every_tool_is_namespaced_and_described():
    server = build_server(make_settings(SOAR_MCP_MODE="full"))
    for tool in await server.list_tools():
        assert tool.name.startswith("soar_"), tool.name
        assert tool.description, tool.name


async def test_resources_and_prompts_are_registered():
    server = build_server(make_settings())
    uris = {str(resource.uri) for resource in await server.list_resources()}
    assert "soar://reference/datapaths" in uris
    assert {p.name for p in await server.list_prompts()} >= {"debug_playbook_run"}


@respx.mock
async def test_list_containers_renders_a_table_end_to_end():
    respx.get(f"{BASE}/rest/container").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "data": [
                    {
                        "id": 42,
                        "name": "Suspicious login",
                        "label": "events",
                        "status": "new",
                        "severity": "high",
                        "owner_name": None,
                        "artifact_count": 3,
                        "create_time": "2026-08-01T10:00:00Z",
                    }
                ],
            },
        )
    )
    server = build_server(make_settings())
    result = await server.call_tool("soar_list_containers", {"query": "login"})
    rendered = str(result)
    assert "Suspicious login" in rendered
    assert "42" in rendered


@respx.mock
async def test_label_allowlist_blocks_a_write_to_a_forbidden_label():
    respx.get(f"{BASE}/rest/container/42").mock(
        return_value=httpx.Response(200, json={"id": 42, "label": "customer_b"})
    )
    server = build_server(make_settings(SOAR_MCP_ALLOWED_LABELS="customer_a"))
    with pytest.raises(Exception, match="deployment restriction"):
        await server.call_tool("soar_add_comment", {"container_id": 42, "comment": "hi"})


@respx.mock
async def test_refusal_names_neither_the_target_label_nor_the_allowlist():
    # On a multi-tenant instance the allowlist is the customer list; an error
    # message that echoes it lets a caller enumerate every tenant.
    respx.get(f"{BASE}/rest/container/42").mock(
        return_value=httpx.Response(200, json={"id": 42, "label": "customer_b"})
    )
    server = build_server(
        make_settings(SOAR_MCP_ALLOWED_LABELS="customer_a,customer_c")
    )
    with pytest.raises(Exception) as excinfo:
        await server.call_tool("soar_add_comment", {"container_id": 42, "comment": "hi"})
    message = str(excinfo.value)
    for leaked in ("customer_a", "customer_b", "customer_c"):
        assert leaked not in message


@respx.mock
async def test_allowlist_also_gates_reads():
    respx.get(f"{BASE}/rest/container/42").mock(
        return_value=httpx.Response(200, json={"id": 42, "label": "customer_b"})
    )
    server = build_server(make_settings(SOAR_MCP_ALLOWED_LABELS="customer_a"))
    for tool, args in (
        ("soar_get_container", {"container_id": 42}),
        ("soar_list_artifacts", {"container_id": 42}),
        ("soar_list_notes", {"container_id": 42}),
        ("soar_list_comments", {"container_id": 42}),
    ):
        with pytest.raises(Exception, match="deployment restriction"):
            await server.call_tool(tool, args)


@respx.mock
async def test_container_listing_is_scoped_to_permitted_labels():
    route = respx.get(f"{BASE}/rest/container").mock(
        return_value=httpx.Response(200, json={"count": 0, "data": []})
    )
    server = build_server(make_settings(SOAR_MCP_ALLOWED_LABELS="customer_a,customer_c"))
    await server.call_tool("soar_list_containers", {})
    params = route.calls.last.request.url.params
    assert params["_filter_label__in"] == '["customer_a", "customer_c"]'


@respx.mock
async def test_unrestricted_listing_sends_no_label_filter():
    route = respx.get(f"{BASE}/rest/container").mock(
        return_value=httpx.Response(200, json={"count": 0, "data": []})
    )
    server = build_server(make_settings())
    await server.call_tool("soar_list_containers", {})
    assert "_filter_label__in" not in route.calls.last.request.url.params


@respx.mock
async def test_system_info_does_not_enumerate_tenants():
    respx.get(f"{BASE}/rest/system_info").mock(
        return_value=httpx.Response(200, json={"version": "7.1.0"})
    )
    server = build_server(
        make_settings(SOAR_MCP_ALLOWED_LABELS="customer_a,customer_c")
    )
    rendered = str(await server.call_tool("soar_system_info", {}))
    assert "customer_a" not in rendered and "customer_c" not in rendered
    assert "2 label(s)" in rendered


@respx.mock
async def test_asset_credentials_never_reach_the_caller():
    respx.get(f"{BASE}/rest/asset/7").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 7,
                "name": "prod_edr",
                "configuration": {
                    "base_url": "https://api.example.com",
                    "client_secret": "SUPER-SECRET",
                    "ph auth token": "tok_live_abc",
                    "password": "hunter2",
                },
            },
        )
    )
    server = build_server(make_settings())
    rendered = str(await server.call_tool("soar_get_asset", {"asset_ref": "7"}))
    for secret in ("SUPER-SECRET", "tok_live_abc", "hunter2"):
        assert secret not in rendered
    assert "prod_edr" in rendered
    assert "https://api.example.com" in rendered


@respx.mock
async def test_raw_rest_get_is_redacted_too():
    respx.get(f"{BASE}/rest/asset").mock(
        return_value=httpx.Response(
            200, json={"data": [{"configuration": {"api_key": "LEAKME"}}]}
        )
    )
    server = build_server(make_settings())
    rendered = str(await server.call_tool("soar_rest_get", {"path": "asset"}))
    assert "LEAKME" not in rendered


async def test_vpe_block_tool_round_trips_through_the_server():
    server = build_server(make_settings(SOAR_MCP_MODE="readonly"))
    built = await server.call_tool(
        "soar_build_format_block",
        {"name": "Msg", "template": "hello {0}", "parameters": ["container:name"]},
    )
    payload = "".join(
        block.text for block in built.content if getattr(block, "type", "") == "text"
    ).strip()
    decoded = await server.call_tool(
        "soar_decode_vpe_block", {"payload": payload, "summary_only": True}
    )
    assert "format" in str(decoded)


# --- tool annotations -------------------------------------------------------
#
# The block builders are pure local computation; everything else reaches the
# live instance. That distinction is what open_world_hint exists to express, so
# it is pinned here rather than left to whoever adds the next tool.

LOCAL_TOOLS = {
    "soar_build_action_block",
    "soar_build_code_block",
    "soar_build_custom_function_block",
    "soar_build_decision_block",
    "soar_build_format_block",
    "soar_build_playbook_block",
    "soar_decode_vpe_block",
    "soar_encode_vpe_block",
}


async def all_tools():
    server = build_server(make_settings(SOAR_MCP_MODE="full"))
    return await server.list_tools()


async def test_every_tool_is_annotated():
    for tool in await all_tools():
        assert tool.annotations is not None, tool.name
        assert tool.annotations.read_only_hint is not None, tool.name


async def test_local_builders_are_closed_world():
    for tool in await all_tools():
        if tool.name in LOCAL_TOOLS:
            assert tool.annotations.open_world_hint is False, tool.name


async def test_every_instance_tool_is_open_world():
    for tool in await all_tools():
        if tool.name not in LOCAL_TOOLS:
            assert tool.annotations.open_world_hint is True, tool.name


async def test_read_only_hint_matches_the_registration_mode():
    readonly = await tool_names("readonly")
    for tool in await all_tools():
        if tool.name in readonly:
            assert tool.annotations.read_only_hint is True, tool.name
        else:
            assert tool.annotations.read_only_hint is False, tool.name


async def test_deletes_and_execution_are_marked_destructive():
    expected = {
        "soar_delete_container",
        "soar_delete_artifact",
        "soar_replace_custom_list",
        "soar_run_playbook",
        "soar_run_action",
        "soar_rest_post",
        "soar_rest_delete",
    }
    for tool in await all_tools():
        if tool.name in expected:
            assert tool.annotations.destructive_hint is True, tool.name


@respx.mock
async def test_add_comment_posts_to_the_collection_that_actually_works():
    # SOAR answers {"success": true} for container/<id> and
    # container/<id>/comments too, but creates nothing. Pin the one that works.
    respx.get(f"{BASE}/rest/container/42").mock(
        return_value=httpx.Response(200, json={"id": 42, "label": "lab"})
    )
    route = respx.post(f"{BASE}/rest/container_comment").mock(
        return_value=httpx.Response(200, json={"success": True, "id": 134})
    )
    server = build_server(make_settings())
    result = await server.call_tool(
        "soar_add_comment", {"container_id": 42, "comment": "hello"}
    )
    assert route.called
    assert json.loads(route.calls.last.request.content) == {
        "container_id": 42,
        "comment": "hello",
    }
    assert "134" in str(result)
