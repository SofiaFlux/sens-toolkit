from sens_mcp import discovery


def test_resolve_operator_exact_alias():
    result = discovery.resolve_operator("enea")
    assert result is not None
    assert result["osd"] == "Enea Operator Sp. z o.o."
    assert result["default_retailer"] == "Enea S.A."


def test_resolve_operator_city_alias():
    result = discovery.resolve_operator("Kraków")
    assert result is not None
    assert result["osd"] == "TAURON Dystrybucja S.A."


def test_resolve_operator_typo_tolerance():
    # "tauorn" is a transposition typo of "tauron"
    result = discovery.resolve_operator("tauorn")
    assert result is not None
    assert result["osd"] == "TAURON Dystrybucja S.A."


def test_resolve_operator_unresolvable():
    result = discovery.resolve_operator("xqzwv frobnicate qqqjjj")
    assert result is None


def test_resolve_operator_empty_query():
    assert discovery.resolve_operator("") is None
    assert discovery.resolve_operator("   ") is None


def test_resolve_operator_candidates_returns_suggestions():
    candidates = discovery.resolve_operator_candidates("taurn")
    assert candidates
    assert "TAURON Dystrybucja S.A." in candidates


def test_search_tariffs_home_filters_to_g_group():
    results = discovery.search_tariffs("home")
    codes = {r["code"] for r in results}
    assert codes == {"G11", "G12", "G12w", "G13"}


def test_search_tariffs_zone_preference_narrows_results():
    results = discovery.search_tariffs("home", zone_preference="2-zone-weekend")
    codes = {r["code"] for r in results}
    assert codes == {"G12w"}


def test_search_tariffs_industry():
    results = discovery.search_tariffs("industry")
    codes = {r["code"] for r in results}
    assert codes == {"B21", "B22", "B23", "A21", "A23"}


def test_search_tariffs_small_business():
    results = discovery.search_tariffs("small_business")
    codes = {r["code"] for r in results}
    assert codes == {"C11", "C12a", "C12b"}


def test_known_tariff_codes_nonempty():
    assert "G11" in discovery.known_tariff_codes()
