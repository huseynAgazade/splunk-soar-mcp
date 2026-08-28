import httpx
import pytest
import respx
from conftest import BASE, make_settings

from splunk_soar_mcp.client import SoarClient, _quoted
from splunk_soar_mcp.errors import NotFoundError, SoarError


@pytest.fixture
async def client():
    instance = SoarClient(make_settings())
    yield instance
    await instance.aclose()


def test_filter_values_are_quoted():
    assert _quoted("triage") == '"triage"'
    assert _quoted(42) == '"42"'


@respx.mock
async def test_search_sends_quoted_icontains_filter(client):
    route = respx.get(f"{BASE}/rest/playbook").mock(
        return_value=httpx.Response(200, json={"count": 0, "data": []})
    )
    await client.search("playbook", "triage", page_size=5)

    params = route.calls.last.request.url.params
    assert params["_filter_name__icontains"] == '"triage"'
    assert params["page_size"] == "5"


@respx.mock
async def test_page_size_is_clamped(client):
    route = respx.get(f"{BASE}/rest/container").mock(
        return_value=httpx.Response(200, json={"count": 0, "data": []})
    )
    await client.search("container", page_size=99_999)
    assert route.calls.last.request.url.params["page_size"] == "500"


@respx.mock
async def test_resolve_prefers_an_exact_name_match(client):
    respx.get(f"{BASE}/rest/playbook").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 2,
                "data": [{"id": 1, "name": "Triage Backfill"}, {"id": 2, "name": "Triage"}],
            },
        )
    )
    respx.get(f"{BASE}/rest/playbook/2").mock(
        return_value=httpx.Response(200, json={"id": 2, "name": "Triage"})
    )
    assert (await client.resolve("playbook", "Triage"))["id"] == 2


@respx.mock
async def test_resolve_passes_numeric_ids_straight_through(client):
    route = respx.get(f"{BASE}/rest/playbook/77").mock(
        return_value=httpx.Response(200, json={"id": 77, "name": "By Id"})
    )
    assert (await client.resolve("playbook", "77"))["id"] == 77
    assert route.called


@respx.mock
async def test_resolve_raises_when_nothing_matches(client):
    respx.get(f"{BASE}/rest/playbook").mock(
        return_value=httpx.Response(200, json={"count": 0, "data": []})
    )
    with pytest.raises(NotFoundError, match="nope"):
        await client.resolve("playbook", "nope", label="playbook")


@respx.mock
async def test_404_becomes_not_found(client):
    respx.get(f"{BASE}/rest/container/9999").mock(return_value=httpx.Response(404, text="gone"))
    with pytest.raises(NotFoundError):
        await client.get("container/9999")


@respx.mock
async def test_500_becomes_soar_error_with_status(client):
    respx.get(f"{BASE}/rest/app").mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(SoarError) as excinfo:
        await client.get("app")
    assert excinfo.value.status == 500


@respx.mock
async def test_auth_token_is_sent(client):
    route = respx.get(f"{BASE}/rest/system_info").mock(
        return_value=httpx.Response(200, json={"version": "7.1.0"})
    )
    await client.get("system_info")
    assert route.calls.last.request.headers["ph-auth-token"] == "test-token"


@respx.mock
async def test_none_params_are_dropped(client):
    route = respx.get(f"{BASE}/rest/container").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    await client.get("container", page_size=5, label=None)
    assert "label" not in route.calls.last.request.url.params
