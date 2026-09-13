import httpx
import pytest
import respx

from sens_mcp import server


@pytest.fixture(autouse=True)
def _fresh_client(monkeypatch):
    monkeypatch.setenv("SENS_API_KEY", "test-key-123")
    monkeypatch.setenv("SENS_BASE_URL", "https://api.getsens.energy")
    server._client = None
    yield
    server._client = None


@respx.mock
async def test_unknown_tariff_id_is_not_reported_as_successful_empty_components():
    components = respx.get("https://api.getsens.energy/api/v1/tariffs/components").mock(
        return_value=httpx.Response(200, json={"data": [], "page": 0, "size": 500, "total": 0})
    )
    catalog = respx.get("https://api.getsens.energy/api/v1/tariffs").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"tariff_id": "real_g11_2026", "tariff_code": "G11"}],
                "page": 0,
                "size": 1000,
                "total": 1,
            },
        )
    )

    result = await server.get_tariff_components("definitely-not-a-real-tariff")

    assert components.called
    assert catalog.called
    assert result["status"] == "error"
    assert result["error_code"] == "NOT_FOUND"
    assert "definitely-not-a-real-tariff" in result["message"]


@respx.mock
async def test_known_tariff_with_zero_components_remains_successful_empty_result():
    components = respx.get("https://api.getsens.energy/api/v1/tariffs/components").mock(
        return_value=httpx.Response(200, json={"data": [], "page": 0, "size": 500, "total": 0})
    )
    catalog = respx.get("https://api.getsens.energy/api/v1/tariffs").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"tariff_id": "known-empty-tariff", "tariff_code": "G11"}],
                "page": 0,
                "size": 1000,
                "total": 1,
            },
        )
    )

    result = await server.get_tariff_components("known-empty-tariff")

    assert components.called
    assert catalog.called
    assert result["status"] == "ok"
    assert result["data"] == []


@respx.mock
async def test_empty_component_existence_check_walks_catalog_pages_until_match():
    components = respx.get("https://api.getsens.energy/api/v1/tariffs/components").mock(
        return_value=httpx.Response(200, json={"data": [], "page": 0, "size": 500, "total": 0})
    )

    def catalog_response(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "0"))
        if page == 0:
            return httpx.Response(
                200,
                json={
                    "data": [{"tariff_id": "other"}],
                    "page": 0,
                    "size": 1000,
                    "total": 1001,
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [{"tariff_id": "known-on-page-two"}],
                "page": 1,
                "size": 1000,
                "total": 1001,
            },
        )

    catalog = respx.get("https://api.getsens.energy/api/v1/tariffs").mock(side_effect=catalog_response)

    result = await server.get_tariff_components("known-on-page-two")

    assert components.called
    assert catalog.call_count == 2
    assert result["status"] == "ok"
    assert result["data"] == []
