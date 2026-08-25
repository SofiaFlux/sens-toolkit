import asyncio

import httpx
import respx

from sens_mcp.client import SensClient


def test_headers_include_client_type_for_cost_analysis():
    """X-Client-Type: mcp tags all sens_mcp-originated traffic so the API gateway's
    RateLimitingService can record which usage came through the MCP server, for later
    cost/usage analysis (rate-limit values themselves are unaffected)."""
    client = SensClient(base_url="https://api.getsens.energy", api_key="k")

    headers = client._headers()

    assert headers["X-Client-Type"] == "mcp"
    assert headers["Accept"] == "application/json"
    assert headers["X-API-KEY"] == "k"


@respx.mock
async def test_metadata_refresh_retries_after_transient_failure():
    """Regression test: a failed _refresh_metadata() call used to set
    _known_tariff_codes = [] (which is `is not None`), permanently
    disabling all future retries for the client's lifetime. It should
    instead leave the field as None so a later call can succeed.
    """
    client = SensClient(base_url="https://api.getsens.energy", api_key="k")

    route = respx.get("https://api.getsens.energy/api/v1/tariffs").mock(
        side_effect=httpx.ConnectError("boom")
    )

    await client.ensure_metadata()
    assert client._known_tariff_codes is None
    assert client.known_tariff_codes == []
    assert route.call_count == 1

    # Now let it succeed - a later call must actually retry, not short-circuit.
    route.side_effect = None
    route.return_value = httpx.Response(200, json={"items": [{"tariff_code": "G11"}]})

    await client.ensure_metadata()
    assert client._known_tariff_codes == ["G11"]
    assert route.call_count == 2

    await client.aclose()


@respx.mock
async def test_aclose_awaits_cancelled_background_task():
    """Regression test: aclose() used to cancel the background metadata task
    and immediately close the shared httpx client on the next line, without
    awaiting the cancellation - racing a still in-flight request against
    client teardown. aclose() must complete without raising.
    """
    client = SensClient(base_url="https://api.getsens.energy", api_key="k")

    async def slow_response(request):
        await asyncio.sleep(0.2)
        return httpx.Response(200, json={"items": []})

    respx.get("https://api.getsens.energy/api/v1/tariffs").mock(side_effect=slow_response)

    client.start_background_refresh()
    assert client._metadata_task is not None

    await client.aclose()

    assert client._metadata_task.done()
    assert client._client is None
