from sens_mcp.formatter import format_price_response, format_tariffs_markdown

SAMPLE_PAYLOAD = {
    "meta": {
        "mode": "party_sheet",
        "date": "2026-08-21",
        "pricing_basis": "net_pln",
        "resolved": {"osd": "TAURON Dystrybucja S.A.", "taryfa": "G12w"},
        "lastUpdatedAt": "2026-08-20T10:00:00Z",
        "pagination": {"page": 0, "size": 100, "has_more": False},
    },
    "catalog": {"parties": ["irrelevant", "verbose", "catalog", "data"]},
    "offers": [
        {
            "tariff_code": "G12w",
            "region": "Małopolskie",
            "variant": None,
            "zones": ["day", "night"],
            "supply": {"raw": "internal-blob", "source_value": 1.23, "source_unit": "pln/mwh"},
            "distribution": {"internal_id": "abc123"},
            "summary": {
                "total_avg_pln_per_kwh": 0.85,
                "energy_avg_pln_per_kwh": 0.55,
                "source_value": 999,
                "source_unit": "raw-unit",
            },
        }
    ],
    "unmatched": [],
    "warnings": [],
}


def test_summary_strips_audit_fields():
    result = format_price_response(SAMPLE_PAYLOAD, detail_level="summary")

    assert "catalog" not in result
    offer = result["offers"][0]
    assert offer["summary"]["total_avg_pln_per_kwh"] == 0.85
    assert "source_value" not in offer["summary"]
    assert "source_unit" not in offer["summary"]


def test_summary_keeps_core_meta_fields():
    result = format_price_response(SAMPLE_PAYLOAD, detail_level="summary")
    assert result["meta"]["mode"] == "party_sheet"
    assert result["meta"]["resolved"]["osd"] == "TAURON Dystrybucja S.A."


def test_detailed_returns_payload_unmodified():
    result = format_price_response(SAMPLE_PAYLOAD, detail_level="detailed")
    assert result is SAMPLE_PAYLOAD


def test_summary_always_emits_warnings_list():
    result = format_price_response(SAMPLE_PAYLOAD, detail_level="summary")
    assert result["warnings"] == []

    payload = dict(SAMPLE_PAYLOAD)
    payload["warnings"] = [{"code": "ambiguous_operator", "message": "did you mean: [...]"}]
    result = format_price_response(payload, detail_level="summary")
    assert result["warnings"] == payload["warnings"]

    payload = {k: v for k, v in SAMPLE_PAYLOAD.items() if k != "warnings"}
    result = format_price_response(payload, detail_level="summary")
    assert result["warnings"] == []


def test_format_tariffs_markdown_empty():
    assert "No tariffs" in format_tariffs_markdown([])


def test_format_tariffs_markdown_table():
    rows = [
        {"tariff_code": "G11", "operator_name": "TAURON", "tariff_type": "home", "zone_count": 1, "region": "Małopolskie"},
    ]
    md = format_tariffs_markdown(rows)
    assert "G11" in md
    assert "TAURON" in md
    assert md.startswith("| Code |")
