import httpx
import pytest
import respx
from conftest import BASE, make_settings

from splunk_soar_mcp.server import build_server

ADMIN_READS = {
    "soar_get_system_settings", "soar_get_license", "soar_get_system_health",
    "soar_list_cluster_nodes", "soar_list_feature_flags", "soar_list_ingestion_status",
    "soar_list_container_statuses", "soar_list_severities", "soar_list_custom_fields",
    "soar_list_cef_fields", "soar_list_workbooks", "soar_get_workbook",
    "soar_list_users", "soar_get_user", "soar_list_roles", "soar_get_role",
}
ROLE_WRITES = {"soar_create_role", "soar_update_role", "soar_delete_role"}


async def names(mode: str) -> set[str]:
    server = build_server(make_settings(SOAR_MCP_MODE=mode))
    return {t.name for t in await server.list_tools()}


async def test_admin_reads_are_available_even_in_readonly():
    assert await names("readonly") >= ADMIN_READS


async def test_role_management_requires_full_mode():
    assert not (ROLE_WRITES & await names("standard"))
    assert await names("full") >= ROLE_WRITES


async def test_list_creation_is_standard_but_deletion_is_full():
    standard, full = await names("standard"), await names("full")
    assert {"soar_create_custom_list", "soar_update_custom_list_row"} <= standard
    assert "soar_delete_custom_list" not in standard
    assert "soar_delete_custom_list" in full


@respx.mock
async def test_system_settings_lists_sections_when_none_requested():
    respx.get(f"{BASE}/rest/system_settings").mock(
        return_value=httpx.Response(
            200, json={"email_settings": {"from_email": "a@b.c"}, "fips": {"enabled": False}}
        )
    )
    server = build_server(make_settings())
    out = str(await server.call_tool("soar_get_system_settings", {}))
    assert "email_settings" in out and "fips" in out


@respx.mock
async def test_system_settings_redacts_a_section():
    respx.get(f"{BASE}/rest/system_settings").mock(
        return_value=httpx.Response(
            200, json={"google_maps_settings": {"google_maps_key": "AIzaLEAKME"}}
        )
    )
    server = build_server(make_settings())
    out = str(
        await server.call_tool(
            "soar_get_system_settings", {"section": "google_maps_settings"}
        )
    )
    assert "AIzaLEAKME" not in out


@respx.mock
async def test_unknown_section_lists_the_valid_ones():
    respx.get(f"{BASE}/rest/system_settings").mock(
        return_value=httpx.Response(200, json={"fips": {}, "cloud": {}})
    )
    server = build_server(make_settings())
    out = str(await server.call_tool("soar_get_system_settings", {"section": "nope"}))
    assert "No section named" in out and "fips" in out


@respx.mock
async def test_immutable_roles_cannot_be_edited():
    respx.get(f"{BASE}/rest/role/1").mock(
        return_value=httpx.Response(
            200, json={"id": 1, "name": "Administrator", "immutable": True}
        )
    )
    server = build_server(make_settings(SOAR_MCP_MODE="full"))
    with pytest.raises(Exception, match="platform built-in"):
        await server.call_tool("soar_update_role", {"role_ref": "1", "description": "x"})


@respx.mock
async def test_immutable_roles_cannot_be_deleted():
    respx.get(f"{BASE}/rest/role/1").mock(
        return_value=httpx.Response(
            200, json={"id": 1, "name": "Administrator", "immutable": True}
        )
    )
    server = build_server(make_settings(SOAR_MCP_MODE="full"))
    with pytest.raises(Exception, match="platform built-in"):
        await server.call_tool(
            "soar_delete_role", {"role_ref": "1", "confirm_name": "Administrator"}
        )


@respx.mock
async def test_role_delete_requires_the_exact_name():
    respx.get(f"{BASE}/rest/role/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "name": "temp", "immutable": False})
    )
    delete = respx.delete(f"{BASE}/rest/role/5").mock(return_value=httpx.Response(200, json={}))
    server = build_server(make_settings(SOAR_MCP_MODE="full"))
    out = str(await server.call_tool("soar_delete_role", {"role_ref": "5", "confirm_name": "wrong"}))
    assert "Refusing to delete" in out
    assert not delete.called


@respx.mock
async def test_unknown_permission_area_is_rejected_before_the_call():
    post = respx.post(f"{BASE}/rest/role").mock(return_value=httpx.Response(200, json={"id": 9}))
    server = build_server(make_settings(SOAR_MCP_MODE="full"))
    out = str(
        await server.call_tool(
            "soar_create_role", {"name": "x", "permissions": {"nonsense": {"view": "allow"}}}
        )
    )
    assert "Unknown permission area" in out
    assert not post.called


@respx.mock
async def test_unspecified_permission_verbs_default_to_deny():
    respx.post(f"{BASE}/rest/role").mock(return_value=httpx.Response(200, json={"id": 9}))
    route = respx.post(f"{BASE}/rest/role")
    server = build_server(make_settings(SOAR_MCP_MODE="full"))
    await server.call_tool(
        "soar_create_role", {"name": "x", "permissions": {"containers": {"view": "allow"}}}
    )
    import json as _json

    sent = _json.loads(route.calls.last.request.content)
    entry = sent["permissions"][0]
    assert entry["view"] == "allow"
    assert entry["edit"] == entry["delete"] == entry["execute"] == "deny"


@respx.mock
async def test_custom_list_delete_requires_the_exact_name():
    respx.get(f"{BASE}/rest/decided_list/3").mock(
        return_value=httpx.Response(200, json={"id": 3, "name": "keepme", "content": []})
    )
    delete = respx.delete(f"{BASE}/rest/decided_list/3").mock(
        return_value=httpx.Response(200, json={})
    )
    server = build_server(make_settings(SOAR_MCP_MODE="full"))
    out = str(
        await server.call_tool(
            "soar_delete_custom_list", {"list_ref": "3", "confirm_name": "oops"}
        )
    )
    assert "Refusing to delete" in out
    assert not delete.called


@respx.mock
async def test_row_update_rejects_an_out_of_range_index():
    respx.get(f"{BASE}/rest/decided_list/3").mock(
        return_value=httpx.Response(200, json={"id": 3, "name": "l", "content": [["a"]]})
    )
    post = respx.post(f"{BASE}/rest/decided_list/3").mock(
        return_value=httpx.Response(200, json={})
    )
    server = build_server(make_settings())
    out = str(
        await server.call_tool(
            "soar_update_custom_list_row", {"list_ref": "3", "row_index": 7, "row": ["z"]}
        )
    )
    assert "out of range" in out
    assert not post.called
