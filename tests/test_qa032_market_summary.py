from sens_mcp.formatter import format_price_response


def _market_payload() -> dict:
    return {
        "meta": {
            "mode": "market_pair",
            "date": "2026-09-10",
            "resolved": {"market": "rdn", "osd": "TAURON Dystrybucja S.A."},
            "fx": {
                "pair": "EUR/PLN",
                "rate": 4.2512,
                "table_no": "178/A/NBP/2026",
                "rate_date": "2026-09-10",
            },
        },
        "offers": [
            {
                "tariff_code": "G11",
                "zones": ["flat"],
                "supply": {
                    "source": "market",
                    "market": "rdn",
                    "series": "ENTSOE_DAY_AHEAD",
                    "granularity": "PT15M",
                    "currency_conversion": "NBP",
                    "points": [
                        {
                            "hour": 0,
                            "minute": 0,
                            "source_eur_per_mwh": 88.0,
                            "energy_pln_per_kwh": 0.374106,
                            "total_pln_per_kwh": 0.620506,
                        },
                        {
                            "hour": 0,
                            "minute": 15,
                            "source_eur_per_mwh": 89.0,
                            "energy_pln_per_kwh": 0.378357,
                            "total_pln_per_kwh": 0.624757,
                        },
                    ],
                    "raw": "must be stripped",
                },
                "distribution": {
                    "source": "tariff",
                    "operator": "TAURON Dystrybucja S.A.",
                    "tariff_id": "tauron_g11_2026",
                },
                "summary": {"energy_avg_pln_per_kwh": 0.3762315},
            }
        ],
        "warnings": [],
    }


def test_summary_preserves_market_fx_and_time_series_facts():
    result = format_price_response(_market_payload(), detail_level="summary")

    assert result["meta"]["fx"] == _market_payload()["meta"]["fx"]
    supply = result["offers"][0]["supply"]
    assert supply["source"] == "market"
    assert supply["market"] == "rdn"
    assert supply["series"] == "ENTSOE_DAY_AHEAD"
    assert supply["granularity"] == "PT15M"
    assert supply["currency_conversion"] == "NBP"
    assert supply["points"] == _market_payload()["offers"][0]["supply"]["points"]
    assert "raw" not in supply


def test_summary_still_omits_regular_tariff_supply_for_token_economy():
    payload = _market_payload()
    payload["meta"].pop("fx")
    payload["offers"][0]["supply"] = {
        "source": "tariff",
        "operator": "TAURON Sprzedaż Sp. z o.o.",
        "tariff_id": "tauron_sale_g11_2026",
        "variable": [{"name": "energia", "value_pln_per_kwh": 0.5}],
    }

    result = format_price_response(payload, detail_level="summary")

    assert "fx" not in result["meta"]
    assert "supply" not in result["offers"][0]
