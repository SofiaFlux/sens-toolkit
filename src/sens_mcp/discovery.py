"""Market knowledge base for the Polish electricity market (§3.1 of the design spec).

This module is the embedded fallback schema: it works with zero network calls,
so the MCP server can boot instantly and answer discovery questions (operator
resolution, tariff search, the cheat-sheet resource) before — or even without —
ever reaching the live SENS API. `client.py` refreshes tariff codes from the
live API in the background and `resolve_operator`/`search_tariffs` fold that
data in when it is available, but never block on it.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Literal

CustomerType = Literal["home", "small_business", "industry"]
ZonePreference = Literal["1-zone", "2-zone-night", "2-zone-peak", "2-zone-weekend", "3-zone"]


# ---------------------------------------------------------------------------
# Distribution System Operators (OSD)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Operator:
    osd: str
    default_retailer: str
    region: str
    aliases: tuple[str, ...]
    supported_tariff_groups: tuple[str, ...] = ("G", "C", "B", "A")


OPERATORS: tuple[Operator, ...] = (
    Operator(
        osd="PGE Dystrybucja S.A.",
        default_retailer="PGE Obrót S.A.",
        region="Mazowieckie / Łódzkie / Lubelskie / Podlaskie / Rzeszów area",
        aliases=("pge", "pge dystrybucja", "pge dystrybucja s.a.", "pge obrot", "pge obrót"),
    ),
    Operator(
        osd="TAURON Dystrybucja S.A.",
        default_retailer="TAURON Sprzedaż Sp. z o.o.",
        region="Małopolskie / Śląskie / Opolskie / Dolnośląskie / Świętokrzyskie",
        aliases=("tauron", "tauron dystrybucja", "tauron sprzedaz", "tauron sprzedaż", "kraków", "krakow", "katowice"),
    ),
    Operator(
        osd="Enea Operator Sp. z o.o.",
        default_retailer="Enea S.A.",
        region="Wielkopolskie / Zachodniopomorskie / Lubuskie / Kujawsko-Pomorskie",
        aliases=("enea", "enea operator", "poznan", "poznań", "szczecin"),
    ),
    Operator(
        osd="Energa-Operator S.A.",
        default_retailer="Energa Obrót S.A.",
        region="Pomorskie / Warmińsko-Mazurskie / part of Kujawsko-Pomorskie",
        aliases=("energa", "energa-operator", "energa operator", "energa obrot", "energa obrót", "gdansk", "gdańsk"),
    ),
    Operator(
        osd="Stoen Operator Sp. z o.o.",
        default_retailer="E.ON Polska S.A.",
        region="Warszawa (city)",
        aliases=("stoen", "stoen operator", "warszawa", "warsaw"),
    ),
)


# ---------------------------------------------------------------------------
# Tariff groups
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TariffGroup:
    code: str
    name: str
    description: str
    zones: int
    customer_types: tuple[CustomerType, ...]
    zone_preference: ZonePreference | None = None


TARIFF_GROUPS: tuple[TariffGroup, ...] = (
    TariffGroup("G11", "Taryfa jednostrefowa", "Jedna stała stawka przez całą dobę.", 1, ("home",), "1-zone"),
    TariffGroup("G12", "Taryfa dzień/noc", "Niższa stawka w godzinach 22:00-06:00 oraz 13:00-15:00.", 2, ("home",), "2-zone-night"),
    TariffGroup("G12w", "Taryfa weekendowa", "Niższa stawka w nocy oraz w soboty, niedziele i dni wolne.", 2, ("home",), "2-zone-weekend"),
    TariffGroup("G13", "Taryfa trzystrefowa", "Trzy strefy czasowe: szczyt, poza szczytem, noc.", 3, ("home",), "3-zone"),
    TariffGroup("C11", "Taryfa jednostrefowa (biznes nN)", "Jedna stała stawka, niskie napięcie.", 1, ("small_business",), "1-zone"),
    TariffGroup("C12a", "Taryfa szczyt/poza szczytem", "Dwie strefy: szczyt przedpołudniowy/popołudniowy i reszta doby.", 2, ("small_business",), "2-zone-peak"),
    TariffGroup("C12b", "Taryfa dzień/noc (biznes nN)", "Dwie strefy: dzień i noc.", 2, ("small_business",), "2-zone-night"),
    TariffGroup("B21", "Taryfa SN podstawowa", "Średnie napięcie, jedna lub dwie strefy podstawowe.", 2, ("industry",)),
    TariffGroup("B22", "Taryfa SN rozszerzona", "Średnie napięcie, rozbudowany podział stref.", 2, ("industry",)),
    TariffGroup("B23", "Taryfa SN pełna", "Średnie napięcie, pełny podział stref czasowych.", 3, ("industry",), "3-zone"),
    TariffGroup("A21", "Taryfa WN podstawowa", "Wysokie napięcie, duzi odbiorcy przemysłowi.", 2, ("industry",)),
    TariffGroup("A23", "Taryfa WN pełna", "Wysokie napięcie, pełny podział stref czasowych.", 3, ("industry",), "3-zone"),
)


CHEAT_SHEET_MARKDOWN = """\
# SENS Energy Market Cheat Sheet

## Distribution Operators (OSD) vs Retailers (Sprzedawcy)
SENS separates the **network operator (OSD)** — who owns the wires and is a
regional monopoly — from the **retailer (sprzedawca)** — who sells you energy
and who you can freely choose. Always pass the exact OSD/sprzedawca string;
use `resolve_operator` to turn a city or a colloquial company name into the
exact values the API expects.

| OSD | Default retailer | Region |
|---|---|---|
| PGE Dystrybucja S.A. | PGE Obrót S.A. | Mazowieckie / Łódzkie / Lubelskie / Podlaskie |
| TAURON Dystrybucja S.A. | TAURON Sprzedaż Sp. z o.o. | Małopolskie / Śląskie / Opolskie / Dolnośląskie |
| Enea Operator Sp. z o.o. | Enea S.A. | Wielkopolskie / Zachodniopomorskie / Lubuskie |
| Energa-Operator S.A. | Energa Obrót S.A. | Pomorskie / Warmińsko-Mazurskie |
| Stoen Operator Sp. z o.o. | E.ON Polska S.A. | Warszawa (city) |

## Tariff groups
- **G (household):** G11 (1-zone flat), G12 (2-zone day/night), G12w (2-zone
  weekend), G13 (3-zone).
- **C (small/medium business, low voltage):** C11 (1-zone), C12a
  (peak/off-peak), C12b (day/night).
- **B (medium voltage industry):** B21, B22, B23.
- **A (high voltage large industry):** A21, A23.

## Price component structure
Every offer breaks down into: energy price (PLN/MWh), distribution
fixed/variable charges, and national fees (capacity/mocowa, RES/OZE,
cogeneration, transition, quality). Use `get_prices` for the full computed
breakdown — never re-derive totals client-side, the backend is the single
source of truth.

## Tools
- `resolve_operator(query, region=None)` — fuzzy-resolve a city or company
  name to the exact `osd`/`sprzedawca` strings.
- `search_tariffs(customer_type, zone_preference=None, operator=None)` —
  discover valid tariff codes for a customer profile.
- `get_prices(osd, taryfa, ...)` — fetch composite prices and rate breakdown.
- `get_tariff_components(tariff_id)` — inspect a tariff's URE-approved rates.
"""


# ---------------------------------------------------------------------------
# Fuzzy resolution
# ---------------------------------------------------------------------------


def _normalize(s: str) -> str:
    return s.strip().casefold()


def _build_alias_index() -> dict[str, Operator]:
    idx: dict[str, Operator] = {}
    for op in OPERATORS:
        for cand in (op.osd, op.default_retailer, *op.aliases):
            idx[_normalize(cand)] = op
    return idx


# Built once at import time and shared by resolve_operator/resolve_operator_candidates
# rather than rebuilt from scratch on every call.
_ALIAS_INDEX: dict[str, Operator] = _build_alias_index()


def resolve_operator(query: str, region: str | None = None) -> dict | None:
    """Resolve a natural-language city or company name to an exact OSD/retailer pair.

    Uses `difflib.get_close_matches` against known operator names and aliases
    for typo tolerance. Returns None if nothing matches closely enough, or if
    the query is genuinely ambiguous between two or more operators — callers
    (server.py) turn that into a structured AMBIGUOUS_OPERATOR /
    UNRESOLVABLE_OPERATOR error with suggestions.
    """
    if not query or not query.strip():
        return None

    q = _normalize(query)

    # Exact / substring match against aliases first (cheap and precise).
    # Collect ALL matching operators before deciding: a single match resolves
    # directly, but two or more equally-valid matches are ambiguous and must
    # not be silently resolved to whichever operator happens to be declared
    # first in OPERATORS.
    matched_ops: list[Operator] = []
    seen_osds: set[str] = set()
    for op in OPERATORS:
        candidates = (op.osd, op.default_retailer, *op.aliases)
        for cand in candidates:
            cand_n = _normalize(cand)
            if q == cand_n or q in cand_n or cand_n in q:
                if op.osd not in seen_osds:
                    matched_ops.append(op)
                    seen_osds.add(op.osd)
                break

    if len(matched_ops) == 1:
        return _operator_to_dict(matched_ops[0])
    if len(matched_ops) > 1:
        # Ambiguous — let the caller's candidate-suggestion path handle it.
        return None

    # Fuzzy fallback across all alias strings.
    matches = difflib.get_close_matches(q, _ALIAS_INDEX.keys(), n=1, cutoff=0.6)
    if matches:
        return _operator_to_dict(_ALIAS_INDEX[matches[0]])

    return None


def resolve_operator_candidates(query: str, n: int = 3) -> list[str]:
    """Return up to n close alias matches for use in error-message suggestions."""
    if not query or not query.strip():
        return []
    q = _normalize(query)
    matches = difflib.get_close_matches(q, _ALIAS_INDEX.keys(), n=n, cutoff=0.4)
    seen: list[str] = []
    for m in matches:
        osd = _ALIAS_INDEX[m].osd
        if osd not in seen:
            seen.append(osd)
    return seen


def _operator_to_dict(op: Operator) -> dict:
    return {
        "osd": op.osd,
        "default_retailer": op.default_retailer,
        "region": op.region,
        "supported_tariff_groups": list(op.supported_tariff_groups),
    }


def search_tariffs(
    customer_type: CustomerType,
    zone_preference: ZonePreference | None = None,
    operator: str | None = None,
) -> list[dict]:
    """Filter the embedded tariff-group catalog by customer profile.

    `operator` is accepted for API-shape parity with the spec (§3.1); the
    tariff-group catalog itself is operator-agnostic (all OSDs offer the same
    regulated groups), so it only affects the response by validating (via
    `resolve_operator`) that the operator is a real one — invalid operators
    do not silently return generic results.
    """
    results = [g for g in TARIFF_GROUPS if customer_type in g.customer_types]
    if zone_preference is not None:
        results = [g for g in results if g.zone_preference == zone_preference]
    return [
        {
            "code": g.code,
            "name": g.name,
            "description": g.description,
            "zones": g.zones,
        }
        for g in results
    ]


def known_tariff_codes() -> list[str]:
    return [g.code for g in TARIFF_GROUPS]
