from sens_mcp.formatter import format_price_response


def _market_payload():
    return {
        "meta": {
            "mode": "market_pair",
            "date": "2026-09-10",
            "resolved": {"osd": "TAURON Dystrybucja S.A.", "market": "rdn", "taryfa": "G11"},
            "fx": {"pair": "EUR/PLN", "rate": 4.318, "table_no": "176/A/NBP/2026", "rate_date": "2026-09-10"},
            "internal_id": "drop-me",
        },
        "offers": [
            {
                "tariff_code": "G11",
                "zones": ["flat"],
                "supply": {
                    "source": "market",
                    "market": "rdn",
                    "series": "entsoe_da_prices",
                    "granularity": "quarter_hour",
                    "currency_conversion": "NBP EUR/PLN 4.318",
                    "points": [
                        {"hour": 1, "minute": 0, "energy_pln_per_kwh": 0.42, "source_value": 97.3},
                        {"hour": 1, "minute": 15, "energy_pln_per_kwh": 0.43, "source_value": 99.6},
                    ],
                    "raw": {"drop": True},
                },
                "distribution": {"operator": "TAURON Dystrybucja S.A.", "raw": {"drop": True}},
                "summary": {"energy_avg_pln_per_kwh": 0.425},
            }
        ],
        "warnings": [],
    }


def test_market_summary_keeps_fx_and_market_series_because_they_are_the_requested_product():
    formatted = format_price_response(_market_payload(), detail_level="summary")

    assert formatted["meta"]["fx"] == {
        "pair": "EUR/PLN",
        "rate": 4.318,
        "table_no": "176/A/NBP/2026",
        "rate_date": "2026-09-10",
    }
    supply = formatted["offers"][0]["supply"]
    assert supply["source"] == "market"
    assert supply["market"] == "rdn"
    assert supply["series"] == "entsoe_da_prices"
    assert supply["granularity"] == "quarter_hour"
    assert supply["currency_conversion"] == "NBP EUR/PLN 4.318"
    assert len(supply["points"]) == 2
    assert "source_value" not in supply["points"][0]
    assert "raw" not in supply
    assert "distribution" not in formatted["offers"][0]


def test_ordinary_tariff_summary_still_omits_verbose_supply_slot():
    payload = _market_payload()
    payload["meta"]["mode"] = "party_sheet"
    payload["meta"].pop("fx")
    payload["offers"][0]["supply"] = {
        "source": "tariff",
        "operator": "Example Retailer",
        "tariff_id": "example_g11_2026",
        "variable": [{"name": "energia", "value_pln_per_kwh": 0.5}],
    }

    formatted = format_price_response(payload, detail_level="summary")

    assert "supply" not in formatted["offers"][0]
    assert "fx" not in formatted["meta"]


def test_detailed_market_payload_remains_unmodified():
    payload = _market_payload()
    assert format_price_response(payload, detail_level="detailed") is payload
