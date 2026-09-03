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


def test_resolve_operator_enea_energa_ambiguous():
    # "ene" is a substring of both Enea's alias "enea" and Energa-Operator's
    # alias "energa". Regression test: resolve_operator used to return the
    # first declared match (Enea) without checking for a second equally
    # valid one; it must now report ambiguity instead of silently guessing.
    result = discovery.resolve_operator("ene")
    assert result is None

    candidates = discovery.resolve_operator_candidates("ene")
    assert "Enea Operator Sp. z o.o." in candidates
    assert "Energa-Operator S.A." in candidates


def test_c12a_and_c12b_have_distinct_zone_preference():
    # C12a (peak/off-peak) and C12b (day/night) are different rate
    # structures and must not share the same zone_preference tag.
    c12a = next(g for g in discovery.TARIFF_GROUPS if g.code == "C12a")
    c12b = next(g for g in discovery.TARIFF_GROUPS if g.code == "C12b")
    assert c12a.zone_preference != c12b.zone_preference

    results = discovery.search_tariffs("small_business", zone_preference="2-zone-night")
    codes = {r["code"] for r in results}
    assert codes == {"C12b"}


def test_energa_default_retailer_matches_the_name_in_the_tariff_database():
    """W bazie jest 'ENERGA-OBRÓT S.A.' (z mysnikiem); tabela zwracala 'Energa Obrót S.A.',
    czyli string, ktorego get_prices(sprzedawca=...) nie przyjmuje."""
    op = next(o for o in discovery.OPERATORS if o.osd == "Energa-Operator S.A.")
    assert op.default_retailer == "ENERGA-OBRÓT S.A."


def test_stoen_has_no_fabricated_default_retailer():
    """'E.ON Polska S.A.' nie istnieje w bazie taryf sprzedawcow w ogole (sprawdzone tez
    'innogy' i samo 'E.ON'). Kompas nie moze pokazywac drogi, ktorej nie ma."""
    op = next(o for o in discovery.OPERATORS if o.osd == "Stoen Operator Sp. z o.o.")
    assert op.default_retailer is None
