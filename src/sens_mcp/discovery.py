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
import re
import unicodedata
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
    default_retailer: str | None
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
        default_retailer="ENERGA-OBRÓT S.A.",
        region="Pomorskie / Warmińsko-Mazurskie / part of Kujawsko-Pomorskie",
        aliases=("energa", "energa-operator", "energa operator", "energa obrot", "energa obrót", "gdansk", "gdańsk"),
    ),
    Operator(
        osd="Stoen Operator Sp. z o.o.",
        default_retailer=None,
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
| PGE Dystrybucja S.A. | PGE Obrót S.A. | Mazowieckie / Łódzkie / Lubelskie / Podlaskie / Rzeszów area |
| TAURON Dystrybucja S.A. | TAURON Sprzedaż Sp. z o.o. | Małopolskie / Śląskie / Opolskie / Dolnośląskie / Świętokrzyskie |
| Enea Operator Sp. z o.o. | Enea S.A. | Wielkopolskie / Zachodniopomorskie / Lubuskie / Kujawsko-Pomorskie |
| Energa-Operator S.A. | ENERGA-OBRÓT S.A. | Pomorskie / Warmińsko-Mazurskie / part of Kujawsko-Pomorskie |
| Stoen Operator Sp. z o.o. | *(none available)* | Warszawa (city) |

## Tariff groups
The list below is the embedded offline fallback of common groups. `search_tariffs`
also folds in additional tariff codes discovered from the live SENS catalog when
metadata is available.

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
  name to the exact `osd`/`sprzedawca` strings; when supplied, `region` is a
  constraint/disambiguator and conflicting matches are rejected.
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


_REGION_NOISE = {"part", "of", "area", "city"}


def _normalize_region_fragment(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    asciiish = "".join(ch for ch in folded if not unicodedata.combining(ch))
    tokens = re.findall(r"[a-z0-9]+", asciiish)
    return " ".join(token for token in tokens if token not in _REGION_NOISE)


def _region_matches(op: Operator, region: str | None) -> bool:
    """Match one explicit coverage segment, not arbitrary substrings.

    In particular, `Pomorskie` must not accidentally match the `pomorskie`
    suffix inside `Kujawsko-Pomorskie`. Slash-separated coverage entries are
    authoritative; presentation qualifiers such as `city`, `area`, and
    `part of` are ignored for matching.
    """
    if region is None or not region.strip():
        return True
    requested = _normalize_region_fragment(region)
    if not requested:
        return True
    if requested == _normalize_region_fragment(op.region):
        return True
    return requested in {
        _normalize_region_fragment(part)
        for part in op.region.split("/")
        if _normalize_region_fragment(part)
    }


def _build_alias_index() -> dict[str, Operator]:
    idx: dict[str, Operator] = {}
    for op in OPERATORS:
        candidates = [op.osd, *op.aliases]
        if op.default_retailer is not None:
            candidates.append(op.default_retailer)
        for cand in candidates:
            idx[_normalize(cand)] = op
    return idx


_ALIAS_INDEX: dict[str, Operator] = _build_alias_index()


def resolve_operator(query: str, region: str | None = None) -> dict | None:
    """Resolve a natural-language name; an explicit region constrains the result."""
    if not query or not query.strip():
        return None

    q = _normalize(query)
    matched_ops: list[Operator] = []
    seen_osds: set[str] = set()
    for op in OPERATORS:
        candidates = [op.osd, *op.aliases]
        if op.default_retailer is not None:
            candidates.append(op.default_retailer)
        for cand in candidates:
            cand_n = _normalize(cand)
            if q == cand_n or q in cand_n or cand_n in q:
                if op.osd not in seen_osds:
                    matched_ops.append(op)
                    seen_osds.add(op.osd)
                break

    if region is not None and region.strip():
        matched_ops = [op for op in matched_ops if _region_matches(op, region)]

    if len(matched_ops) == 1:
        return _operator_to_dict(matched_ops[0])
    if len(matched_ops) > 1:
        return None

    # Preserve the old single-best fuzzy behavior when no region was supplied.
    # With a region constraint, keep multiple fuzzy candidates long enough for
    # the region to disambiguate them rather than discarding the hint.
    matches = difflib.get_close_matches(
        q,
        _ALIAS_INDEX.keys(),
        n=5 if region is not None and region.strip() else 1,
        cutoff=0.6,
    )
    fuzzy_ops: list[Operator] = []
    fuzzy_seen: set[str] = set()
    for match in matches:
        op = _ALIAS_INDEX[match]
        if op.osd in fuzzy_seen:
            continue
        if not _region_matches(op, region):
            continue
        fuzzy_ops.append(op)
        fuzzy_seen.add(op.osd)

    if len(fuzzy_ops) == 1:
        return _operator_to_dict(fuzzy_ops[0])
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


def _live_code_customer_type(code: str) -> CustomerType | None:
    """Infer only the broad voltage/customer family encoded in a tariff code.

    This intentionally does not invent zone counts or marketing names for live-only
    codes. Those details remain authoritative in the REST catalog.
    """
    normalized = code.strip().upper()
    if normalized.startswith("G"):
        return "home"
    if normalized.startswith("C"):
        return "small_business"
    if normalized.startswith(("A", "B", "R")):
        return "industry"
    return None


def search_tariffs(
    customer_type: CustomerType,
    zone_preference: ZonePreference | None = None,
    operator: str | None = None,
    live_codes: list[str] | None = None,
) -> list[dict]:
    """Filter the embedded catalog and optionally enrich it with live codes.

    The embedded entries carry curated descriptions and zone metadata. Live-only
    codes are added only when no `zone_preference` is requested, because a bare
    code is not enough evidence to infer its exact zone schedule safely.
    """
    results = [g for g in TARIFF_GROUPS if customer_type in g.customer_types]
    if zone_preference is not None:
        results = [g for g in results if g.zone_preference == zone_preference]

    response = [
        {
            "code": g.code,
            "name": g.name,
            "description": g.description,
            "zones": g.zones,
        }
        for g in results
    ]

    if zone_preference is None and live_codes:
        existing = {row["code"].casefold() for row in response}
        for code in sorted(set(live_codes), key=str.casefold):
            if _live_code_customer_type(code) != customer_type or code.casefold() in existing:
                continue
            response.append(
                {
                    "code": code,
                    "name": "Live SENS catalog tariff",
                    "description": "Discovered from the live SENS tariff catalog; inspect /api/v1/tariffs for authoritative details.",
                    "zones": None,
                }
            )
            existing.add(code.casefold())

    return response


def known_tariff_codes() -> list[str]:
    return [g.code for g in TARIFF_GROUPS]
