from sens_mcp import discovery


def test_resolve_operator_exact_alias():
    result = discovery.resolve_operator("enea")
    assert result is not None
    assert result["dso"] == "Enea Operator Sp. z o.o."
    assert result["default_retailer"] == "Enea S.A."


def test_resolve_operator_city_alias():
    result = discovery.resolve_operator("Kraków")
    assert result is not None
    assert result["dso"] == "TAURON Dystrybucja S.A."


def test_resolve_operator_typo_tolerance():
    # "tauorn" is a transposition typo of "tauron"
    result = discovery.resolve_operator("tauorn")
    assert result is not None
    assert result["dso"] == "TAURON Dystrybucja S.A."


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


def test_search_tariffs_can_include_live_catalog_codes():
    """SENS-QA-20260910-023: search discovery must be able to surface tariff
    codes present in the live REST catalog instead of being permanently limited
    to the embedded fallback subset.
    """
    live_codes = ["G12as", "C11em", "Bt21", "R"]

    home = {r["code"] for r in discovery.search_tariffs("home", live_codes=live_codes)}
    small = {r["code"] for r in discovery.search_tariffs("small_business", live_codes=live_codes)}
    industry = {r["code"] for r in discovery.search_tariffs("industry", live_codes=live_codes)}

    assert "G12as" in home
    assert "C11em" in small
    assert {"Bt21", "R"}.issubset(industry)


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


def test_cheat_sheet_regions_match_operator_table():
    """SENS-QA-20260910-004: the static cheat-sheet resource drifted from the
    OPERATORS table. Every operator region must appear verbatim in the sheet."""
    sheet = discovery.CHEAT_SHEET_MARKDOWN
    for op in discovery.OPERATORS:
        assert op.osd in sheet, f"{op.osd!r} missing from cheat-sheet"
        assert op.region in sheet, (
            f"region {op.region!r} of {op.osd!r} missing from cheat-sheet"
        )


def test_every_operator_osd_resolves_to_exactly_itself():
    """C1 Zadanie 14, krok 3: kazda nazwa OSD z OPERATORS musi rozstrzygac sie przez
    resolve_operator do dokladnie jednego operatora (0 lub >=2 to blad) -- druga polowa
    kryterium 11, na prawdziwej (nie zamockowanej) tablicy OPERATORS."""
    for op in discovery.OPERATORS:
        result = discovery.resolve_operator(op.osd)
        assert result is not None, f"{op.osd!r} failed to resolve to any operator"
        assert result["dso"] == op.osd, (
            f"{op.osd!r} resolved to a different operator: {result['dso']!r}"
        )
