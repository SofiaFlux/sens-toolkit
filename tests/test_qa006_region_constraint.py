from sens_mcp import discovery, server


def test_conflicting_region_rejects_otherwise_exact_city_match():
    assert discovery.resolve_operator("Warszawa", region="Pomorskie") is None


def test_matching_city_region_still_resolves():
    result = discovery.resolve_operator("Warszawa", region="warszawa")
    assert result is not None
    assert result["osd"] == "Stoen Operator Sp. z o.o."


def test_region_matching_is_diacritic_insensitive():
    result = discovery.resolve_operator("tauron", region="Slaskie")
    assert result is not None
    assert result["osd"] == "TAURON Dystrybucja S.A."


def test_region_disambiguates_a_query_matching_multiple_operators():
    result = discovery.resolve_operator("ene", region="Pomorskie")
    assert result is not None
    assert result["osd"] == "Energa-Operator S.A."


def test_mcp_reports_actionable_region_mismatch():
    result = server.resolve_operator("Warszawa", region="Pomorskie")
    assert result["status"] == "error"
    assert result["error_code"] == "REGION_MISMATCH"
    assert "Pomorskie" in result["message"]
    assert "Warszawa (city)" in result["message"]
