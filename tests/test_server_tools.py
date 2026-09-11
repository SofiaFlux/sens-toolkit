import httpx
import pytest
import respx

from sens_mcp import server


@pytest.fixture(autouse=True)
def _fresh_client(monkeypatch):
    """Reset the module-level client and point it at a fixed base URL/key per test."""
    monkeypatch.setenv("SENS_API_KEY", "test-key-123")
    monkeypatch.setenv("SENS_BASE_URL", "https://api.getsens.energy")
    server._client = None
    yield
    server._client = None


@respx.mock
async def test_get_prices_success_summary_mode():
    route = respx.get("https://api.getsens.energy/api/v1/prices").mock(
        return_value=httpx.Response(
            200,
            json={
                "meta": {
                    "mode": "party_sheet",
                    "date": "2026-08-21",
                    "resolved": {"osd": "TAURON Dystrybucja S.A.", "taryfa": "G12w"},
                    "lastUpdatedAt": "2026-08-20T10:00:00Z",
                },
                "offers": [
                    {
                        "tariff_code": "G12w",
                        "region": "Małopolskie",
                        "zones": ["day", "night"],
                        "summary": {
                            "total_avg_pln_per_kwh": 0.85,
                            "source_value": 999,
                        },
                    }
                ],
                "unmatched": [],
                "warnings": [],
            },
        )
    )
    respx.get("https://api.getsens.energy/api/v1/tariffs").mock(
        return_value=httpx.Response(200, json={"items": []})
    )

    result = await server.get_prices(osd="TAURON Dystrybucja S.A.", taryfa="G12w")

    assert route.called
    assert result["status"] == "ok"
    assert result["offers"][0]["tariff_code"] == "G12w"
    assert "source_value" not in result["offers"][0]["summary"]

    request = route.calls.last.request
    assert request.headers["X-API-KEY"] == "test-key-123"


@respx.mock
async def test_get_prices_maps_401_to_structured_error():
    respx.get("https://api.getsens.energy/api/v1/tariffs").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    respx.get("https://api.getsens.energy/api/v1/prices").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )

    result = await server.get_prices(osd="TAURON Dystrybucja S.A.", taryfa="G12w")

    assert result["status"] == "error"
    assert result["error_code"] == "UNAUTHORIZED"
    assert "remediation" in result


@respx.mock
async def test_get_prices_maps_500_to_structured_error():
    respx.get("https://api.getsens.energy/api/v1/tariffs").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    respx.get("https://api.getsens.energy/api/v1/prices").mock(
        return_value=httpx.Response(503, text="service unavailable")
    )

    result = await server.get_prices(osd="TAURON Dystrybucja S.A.", taryfa="G12w")

    assert result["status"] == "error"
    assert result["error_code"] == "UPSTREAM_ERROR"


def test_resolve_operator_tool_success():
    result = server.resolve_operator(query="enea")
    assert result["osd"] == "Enea Operator Sp. z o.o."


def test_resolve_operator_tool_unresolvable_error_shape():
    result = server.resolve_operator(query="xqzwv frobnicate qqqjjj")
    assert result["status"] == "error"
    assert result["error_code"] == "UNRESOLVABLE_OPERATOR"
    assert "known_osds" in result["suggestions"]


async def test_search_tariffs_tool_success():
    result = await server.search_tariffs(customer_type="home", zone_preference="1-zone")
    assert result["status"] == "ok"
    codes = {t["code"] for t in result["tariffs"]}
    assert codes == {"G11"}


async def test_search_tariffs_tool_bad_operator_error_shape():
    result = await server.search_tariffs(customer_type="home", operator="xqzwv frobnicate qqqjjj")
    assert result["status"] == "error"
    assert result["error_code"] == "UNRESOLVABLE_OPERATOR"
    assert "known_osds" in result["suggestions"]


async def test_search_tariffs_tool_ambiguous_operator_error_shape():
    result = await server.search_tariffs(customer_type="home", operator="ene")
    assert result["status"] == "error"
    assert result["error_code"] == "AMBIGUOUS_OPERATOR"
    assert "Enea Operator Sp. z o.o." in result["suggestions"]["did_you_mean"]
    assert "Energa-Operator S.A." in result["suggestions"]["did_you_mean"]


@respx.mock
async def test_search_tariffs_folds_in_live_catalog_metadata():
    """SENS-QA-20260910-023: the MCP tool should enrich its embedded fallback
    with codes that the live tariff catalog actually serves.
    """
    respx.get("https://api.getsens.energy/api/v1/tariffs").mock(
        return_value=httpx.Response(200, json={"data": [{"tariff_code": "G12as"}]})
    )

    result = await server.search_tariffs(customer_type="home")

    assert result["status"] == "ok"
    assert "G12as" in {row["code"] for row in result["tariffs"]}


def test_cheat_sheet_resource_mentions_tariff_groups():
    text = server.market_cheat_sheet()
    assert "G11" in text
    assert "TAURON Dystrybucja" in text


@respx.mock
async def test_get_prices_malformed_offer_shape_returns_structured_error():
    respx.get("https://api.getsens.energy/api/v1/tariffs").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    respx.get("https://api.getsens.energy/api/v1/prices").mock(
        return_value=httpx.Response(200, json={"meta": {}, "offers": ["not-a-dict"]})
    )

    result = await server.get_prices(osd="TAURON Dystrybucja S.A.", taryfa="G12w")

    assert result["status"] == "error"
    assert result["error_code"] == "MALFORMED_RESPONSE"
