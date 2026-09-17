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


def _market_payload(market: str) -> dict:
    if market == "rdn":
        fx = {"pair": "EUR/PLN", "rate": 4.318, "table_no": "176/A/NBP/2026", "rate_date": "2026-09-10"}
        supply = {
            "source": "market",
            "market": "rdn",
            "series": "entsoe_da_prices",
            "granularity": "quarter_hour",
            "currency_conversion": "NBP EUR/PLN",
            "points": [
                {"hour": 1, "minute": 0, "source_eur_per_mwh": 100.0, "energy_pln_per_kwh": 0.4318},
                {"hour": 1, "minute": 15, "source_eur_per_mwh": 101.0, "energy_pln_per_kwh": 0.436118},
            ],
        }
    else:
        fx = None
        supply = {
            "source": "market",
            "market": "rce",
            "series": "pse_rce_pln",
            "granularity": "quarter_hour",
            "currency_conversion": None,
            "points": [
                {"hour": 1, "minute": 0, "energy_pln_per_kwh": 0.5},
                {"hour": 1, "minute": 15, "energy_pln_per_kwh": 0.51},
            ],
        }

    meta = {
        "mode": "market_pair",
        "date": "2026-09-10",
        "resolved": {"dso": "TAURON Dystrybucja S.A.", "market": market, "tariff": "G11"},
    }
    if fx is not None:
        meta["fx"] = fx

    return {
        "meta": meta,
        "offers": [{
            "tariff_code": "G11",
            "zones": ["flat"],
            "supply": supply,
            "summary": {"energy_avg_pln_per_kwh": 0.433959 if market == "rdn" else 0.505},
        }],
        "warnings": [],
        "unmatched": [],
    }


@pytest.mark.parametrize("market", ["rdn", "rce"])
@respx.mock
async def test_market_summary_preserves_the_market_product_required_by_parity_contract(market: str):
    respx.get("https://api.getsens.energy/api/v1/tariffs").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    respx.get("https://api.getsens.energy/api/v1/prices").mock(
        return_value=httpx.Response(200, json=_market_payload(market))
    )

    result = await server.get_prices(
        dso="TAURON Dystrybucja S.A.", tariff="G11", market=market, date="2026-09-10",
        detail_level="summary",
    )

    assert result["status"] == "ok"
    assert result["meta"]["resolved"]["market"] == market
    if market == "rdn":
        assert result["meta"]["fx"]["rate"] == 4.318
    else:
        assert "fx" not in result["meta"]

    supply = result["offers"][0]["supply"]
    assert supply["source"] == "market"
    assert supply["market"] == market
    assert supply["series"] == ("entsoe_da_prices" if market == "rdn" else "pse_rce_pln")
    assert supply["granularity"] == "quarter_hour"
    assert supply["points"] == _market_payload(market)["offers"][0]["supply"]["points"]


@respx.mock
async def test_tariff_summary_still_omits_verbose_supply_slot():
    respx.get("https://api.getsens.energy/api/v1/tariffs").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    payload = {
        "meta": {"mode": "party_sheet", "date": "2026-09-10", "resolved": {"dso": "TAURON Dystrybucja S.A."}},
        "offers": [{
            "tariff_code": "G11",
            "zones": ["flat"],
            "supply": {"source": "tariff", "operator": "TAURON", "tariff_id": "tauron_g11_2026"},
            "summary": {"variable_total_pln_per_kwh": {"flat": 0.2464}},
        }],
        "warnings": [],
    }
    respx.get("https://api.getsens.energy/api/v1/prices").mock(return_value=httpx.Response(200, json=payload))

    result = await server.get_prices(dso="TAURON Dystrybucja S.A.", tariff="G11", detail_level="summary")

    assert result["status"] == "ok"
    assert "supply" not in result["offers"][0]
