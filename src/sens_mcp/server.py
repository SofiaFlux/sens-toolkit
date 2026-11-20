"""FastMCP server definition: Tools and Resources for the SENS Energy Data API.

Implements the actionable self-correction error protocol from design spec
§4: tool errors are returned as structured JSON (`status`, `error_code`,
`message`, `suggestions`/`remediation`) instead of raw HTTP exceptions, so an
LLM driving this server in a ReAct loop can self-repair its next call.
"""

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from . import discovery
from .client import SensApiError, SensClient
from .formatter import format_price_response
from .models import PriceResponse, TariffComponentsResponse

mcp = FastMCP("sens-energy")

_client: SensClient | None = None


def get_client() -> SensClient:
    global _client
    if _client is None:
        _client = SensClient()
        # Kick off metadata refresh in the background as soon as the client
        # exists (design spec §5.1: non-blocking lazy init). ensure_metadata()
        # (awaited inline by client.get_prices/etc.) remains the blocking
        # fallback for the case where this hasn't finished yet.
        _client.start_background_refresh()
    return _client


def _malformed_response_error(exc: Exception) -> dict[str, Any]:
    return {
        "status": "error",
        "error_code": "MALFORMED_RESPONSE",
        "message": f"The SENS API returned an unexpected response shape: {exc}",
        "remediation": "This likely indicates a backend schema change; please report this issue.",
    }


def _operator_resolution_error(
    query: str,
    example_valid_call: str | None = None,
    live_osds: list[str] | None = None,
) -> dict[str, Any]:
    """Shared AMBIGUOUS_OPERATOR / UNRESOLVABLE_OPERATOR error shape."""
    candidates = discovery.resolve_operator_candidates(query, live_osds=live_osds)
    if candidates:
        return {
            "status": "error",
            "error_code": "AMBIGUOUS_OPERATOR",
            "message": (
                f"Operator '{query}' is ambiguous or not an exact match. "
                "SENS separates network distribution (OSD) from energy retail (sprzedawca)."
            ),
            "suggestions": {"did_you_mean": candidates},
            "example_valid_call": example_valid_call or f"resolve_operator(query='{candidates[0]}')",
        }

    known_osds = [op.osd for op in discovery.OPERATORS]
    for osd in live_osds or []:
        if osd not in known_osds:
            known_osds.append(osd)
    return {
        "status": "error",
        "error_code": "UNRESOLVABLE_OPERATOR",
        "message": f"Could not resolve '{query}' to any known OSD or retailer.",
        "suggestions": {
            "known_dsos": known_osds,
        },
        "remediation": "Check sens://market/cheat-sheet or the live tariff catalog for supported operators.",
    }


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("sens://market/cheat-sheet", mime_type="text/markdown")
def market_cheat_sheet() -> str:
    """Polish electricity market cheat sheet: OSDs, tariff groups, price components."""
    return discovery.CHEAT_SHEET_MARKDOWN


@mcp.resource("sens://glossary", mime_type="application/json")
async def glossary() -> str:
    """What every code in SENS responses means: variant groups and keys (BILLING_PERIOD=M1, PHASES=P3, EM_UTILISATION=SM_GT_0_1, ...),
    zone keys, component types, tariff group suffixes, warning codes and time fields. Read it before interpreting variants or warnings."""
    client = get_client()
    resp = await client._ensure_client().get("/glossary.json", headers={"Accept": "application/json"})
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# Discovery tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def resolve_operator(query: str, region: str | None = None) -> dict[str, Any]:
    """Resolve a natural-language city or company name to the exact DSO (distribution
    operator, sometimes called OSD in Polish-market sources) and default retailer
    strings the SENS API expects.

    Example: query="Kraków" or query="enea". Handles typos via fuzzy matching.
    When `region` is supplied it is a constraint/disambiguator, not a passive hint.
    Curated high-confidence operator aliases resolve offline; lower-confidence
    matches consult the live SENS tariff catalog before typo-based fallback.
    """
    # Preserve a zero-network fast path only for high-confidence embedded
    # identity matches. Typo-distance matching is intentionally delayed until
    # live catalog identities have had a chance to match.
    result = discovery.resolve_operator(query, region=region, allow_fuzzy=False)
    if result is not None:
        return result

    # A known curated operator with a conflicting region should retain the
    # dedicated REGION_MISMATCH result without needing a metadata request.
    if region is not None and region.strip():
        unconstrained = discovery.resolve_operator(query, allow_fuzzy=False)
        if unconstrained is not None:
            actual_region = unconstrained.get("region")
            return {
                "status": "error",
                "error_code": "REGION_MISMATCH",
                "message": (
                    f"'{query}' resolves to {unconstrained['dso']} in region "
                    f"'{actual_region}', which conflicts with requested region '{region}'."
                ),
                "suggestions": {
                    "resolved_operator": unconstrained["dso"],
                    "actual_region": actual_region,
                },
                "remediation": "Remove the region constraint or use one of the operator's declared coverage regions.",
            }

    client = get_client()
    await client.ensure_metadata()
    live_osds = client.known_osd_names
    result = discovery.resolve_operator(query, region=region, live_osds=live_osds)
    if result is not None:
        return result

    return _operator_resolution_error(query, live_osds=live_osds)


@mcp.tool()
async def search_tariffs(
    customer_type: Literal["home", "small_business", "industry"],
    zone_preference: Literal["1-zone", "2-zone-night", "2-zone-peak", "2-zone-weekend", "3-zone"] | None = None,
    operator: str | None = None,
) -> dict[str, Any]:
    """Discover valid tariff codes tailored to a customer profile (household,
    small business, or industry), optionally narrowed by zone preference and
    operator. The embedded catalog is enriched with live SENS tariff codes
    when metadata is reachable; discovery still works offline from fallback data.
    """
    if operator is not None:
        resolved = discovery.resolve_operator(operator)
        if resolved is None:
            return _operator_resolution_error(
                operator,
                example_valid_call="search_tariffs(customer_type='home', operator='TAURON Dystrybucja S.A.')",
            )

    client = get_client()
    await client.ensure_metadata()
    return {
        "status": "ok",
        "tariffs": discovery.search_tariffs(
            customer_type,
            zone_preference,
            operator,
            live_codes=client.known_tariff_codes,
        ),
    }


# ---------------------------------------------------------------------------
# Data tools (single source of truth — SENS backend does all calculation)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_prices(
    dso: str,
    tariff: str,
    retailer: str | None = None,
    date: str | None = None,
    market: str | None = None,
    annual_kwh: int | None = None,
    region: str | None = None,
    since: str | None = None,
    detail_level: Literal["summary", "detailed"] = "summary",
    page: int = 0,
    size: int = 100,
) -> dict[str, Any]:
    """Fetch composite electricity prices and rate breakdown for a given DSO +
    tariff, optionally scoped to a retailer, date, market, region, and annual
    consumption. When `annual_kwh` is provided, the backend computes exact
    annual capacity fees and volume-weighted totals — never re-derive these
    client-side.

    `detail_level="summary"` (default) strips verbose audit fields for token
    economy; use `detail_level="detailed"` for the full raw payload.
    """
    client = get_client()
    try:
        payload = await client.get_prices(
            dso=dso,
            retailer=retailer,
            tariff=tariff,
            market=market,
            date=date,
            annual_kwh=annual_kwh,
            region=region,
            since=since,
            page=page,
            size=size,
        )
    except SensApiError as e:
        return e.to_dict()

    try:
        parsed = PriceResponse.model_validate(payload)
        return {"status": "ok", **format_price_response(parsed.model_dump(), detail_level=detail_level)}
    except Exception as e:  # noqa: BLE001 - MCP tool boundary: any parse/validation
        return _malformed_response_error(e)


@mcp.tool()
async def get_tariff_components(tariff_id: str, since: str | None = None) -> dict[str, Any]:
    """Inspect the detailed fixed/variable rate components of a tariff, as
    approved by URE (the Polish energy regulator).
    """
    client = get_client()
    try:
        payload = await client.get_tariff_components(tariff_id, since=since)
        rows = payload.get("data") or payload.get("items") or payload.get("content") or []
        if isinstance(rows, list) and not rows:
            if not await client.tariff_exists(tariff_id):
                return SensApiError(
                    "NOT_FOUND",
                    f"No public tariff exists with tariff_id '{tariff_id}'.",
                    remediation="Check the tariff_id in get_tariffs/search results and retry.",
                ).to_dict()
    except SensApiError as e:
        return e.to_dict()

    try:
        # T1 (18.11): the API answers {data, page, size}; the old {items} model left "items": [] beside the rows, which reads as "no
        # components". Mirror the API (parity with the raw call) and add total; the model only validates the rows.
        TariffComponentsResponse.model_validate({"items": rows})
        out = {k: v for k, v in payload.items() if k not in ("items", "content", "data")}
        return {"status": "ok", **out, "data": rows, "total": payload.get("total", len(rows))}
    except Exception as e:  # noqa: BLE001 - MCP tool boundary: any parse/validation
        return _malformed_response_error(e)


@mcp.tool()
async def get_regulated_fees(
    fee_type: str | None = None,
    customer_scope: str | None = None,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Nationwide regulated electricity fees in Poland, published by the President of URE: the capacity fee (opłata mocowa) --
    lump-sum monthly bands for households and the per-kWh rate for other end users together with its charging window
    (local clock times, e.g. 07:00-22:00 on working days) -- the OZE fee and the cogeneration fee; and the quality fee (stawka
    jakościowa) of the PSE tariff: SoSJ x kok for end users (NON_SPECIAL), SoSJ x kos unrounded for special consumers (SPECIAL),
    each in force until the next PSE decision.

    fee_type: capacity | oze | cogeneration | quality (all when omitted).
    customer_scope: HOUSEHOLD_LUMP_SUM | NON_LUMP_SUM | ALL | NON_SPECIAL | SPECIAL.
    Either `date` (YYYY-MM-DD, rates in force that day; today when nothing is given) or `date_from` + `date_to`
    (every rate whose validity overlaps the range, at most 10 years), e.g. the quarterly business capacity rates of 2027.
    """
    client = get_client()
    try:
        payload = await client.get_regulated_fees(fee_type, customer_scope, date, date_from, date_to)
    except SensApiError as e:
        return e.to_dict()
    if not isinstance(payload.get("data"), list):
        return _malformed_response_error(ValueError("regulated-fees response has no data list"))
    return {"status": "ok", **payload}


@mcp.tool()
async def get_regulatory_indicators(
    indicator: str | None = None,
    tariff_group: str | None = None,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Indicators published by the President of URE (Polish energy regulator): average_market_price (average selling price on the
    competitive market, yearly and quarterly), average_quarterly_price, average_household_price, average_combined_price and
    average_combined_price_80pct (per tariff group and zone), risk_free_rate, co2_forward_price, penalty_rate.

    Either `date` (values whose period contains that day; today when nothing is given) or `date_from` + `date_to` (a series, at most
    10 years). tariff_group filters the per-group averages (e.g. G11). valid_from/valid_to in the result is the period the value refers to.
    """
    client = get_client()
    try:
        payload = await client.get_regulatory_indicators(indicator, tariff_group, date, date_from, date_to)
    except SensApiError as e:
        return e.to_dict()
    if not isinstance(payload.get("data"), list):
        return _malformed_response_error(ValueError("regulatory-indicators response has no data list"))
    return {"status": "ok", **payload}


def main() -> None:
    """Synchronous entrypoint used by __main__.py / the `sens-mcp` console script."""
    mcp.run()
