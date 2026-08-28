import json

import httpx
import pytest
import respx
from conftest import BASE, make_settings

from splunk_soar_mcp.server import build_server

FULL = {"SOAR_MCP_MODE": "full"}


def _container(label="lab"):
    return httpx.Response(200, json={"id": 42, "label": label, "name": "case"})


@respx.mock
async def test_run_action_sends_the_assets_app_id():
    # Without app_id SOAR queues the run and then fails it with "app_id has
    # invalid format" — a failure that looks like success at the call site.
    respx.get(f"{BASE}/rest/container/42").mock(return_value=_container())
    respx.get(f"{BASE}/rest/asset/9").mock(
        return_value=httpx.Response(200, json={"id": 9, "name": "edr_asset", "app": 8})
    )
    route = respx.post(f"{BASE}/rest/action_run").mock(
        return_value=httpx.Response(200, json={"success": True, "action_run_id": 1})
    )
    server = build_server(make_settings(**FULL))
    await server.call_tool(
        "soar_run_action",
        {"action": "no op", "asset": "9", "container_id": 42, "parameters": {"sleep_seconds": 5}},
    )
    target = json.loads(route.calls.last.request.content)["targets"][0]
    assert target["app_id"] == 8
    assert target["assets"] == ["edr_asset"]
    assert target["parameters"] == [{"sleep_seconds": 5}]


@respx.mock
async def test_run_action_refuses_an_asset_with_no_app():
    respx.get(f"{BASE}/rest/container/42").mock(return_value=_container())
    respx.get(f"{BASE}/rest/asset/9").mock(
        return_value=httpx.Response(200, json={"id": 9, "name": "orphan", "app": None})
    )
    post = respx.post(f"{BASE}/rest/action_run").mock(return_value=httpx.Response(200, json={}))
    server = build_server(make_settings(**FULL))
    with pytest.raises(Exception, match="no app associated"):
        await server.call_tool(
            "soar_run_action", {"action": "no op", "asset": "9", "container_id": 42}
        )
    assert not post.called


@respx.mock
async def test_run_playbook_posts_the_resolved_ids():
    respx.get(f"{BASE}/rest/container/42").mock(return_value=_container())
    respx.get(f"{BASE}/rest/playbook/7").mock(
        return_value=httpx.Response(200, json={"id": 7, "name": "Triage"})
    )
    route = respx.post(f"{BASE}/rest/playbook_run").mock(
        return_value=httpx.Response(200, json={"received": True, "playbook_run_id": "99"})
    )
    server = build_server(make_settings(**FULL))
    await server.call_tool(
        "soar_run_playbook", {"playbook_ref": "7", "container_id": 42, "scope": "all"}
    )
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"container_id": 42, "playbook_id": 7, "scope": "all", "run": True}


@respx.mock
async def test_execution_honours_the_label_allowlist():
    respx.get(f"{BASE}/rest/container/42").mock(return_value=_container(label="customer_b"))
    post = respx.post(f"{BASE}/rest/playbook_run").mock(return_value=httpx.Response(200, json={}))
    server = build_server(make_settings(SOAR_MCP_MODE="full", SOAR_MCP_ALLOWED_LABELS="customer_a"))
    with pytest.raises(Exception, match="deployment restriction"):
        await server.call_tool("soar_run_playbook", {"playbook_ref": "7", "container_id": 42})
    assert not post.called


@respx.mock
async def test_action_runs_are_listed_from_the_action_run_layer():
    # app_run only records executions that reached an app, so an action that
    # failed before that would be invisible in a listing built on it.
    route = respx.get(f"{BASE}/rest/action_run").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "data": [
                    {"id": 5, "action": "no op", "status": "failed",
                     "message": "app_id has invalid format", "container": 42},
                ],
            },
        )
    )
    server = build_server(make_settings())
    out = str(await server.call_tool("soar_list_action_runs", {"container_id": 42}))
    assert route.called
    assert "failed" in out and "no op" in out


@respx.mock
async def test_get_action_run_includes_the_app_runs_beneath_it():
    respx.get(f"{BASE}/rest/action_run/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "action": "run query", "status": "success"})
    )
    respx.get(f"{BASE}/rest/app_run").mock(
        return_value=httpx.Response(
            200, json={"count": 1, "data": [{"id": 77, "result_data": [{"rows": 12}]}]}
        )
    )
    server = build_server(make_settings())
    out = str(await server.call_tool("soar_get_action_run", {"run_id": 5}))
    assert "action_run" in out and "app_runs" in out and "result_data" in out
