"""FastMCP server definition: Tools and Resources for the SENS Energy Data API.

Implements the actionable self-correction error protocol from design spec
§4: tool errors are returned as structured JSON (`status`, `error_code`,
`message`, `suggestions`/`remediation`) instead of raw HTTP exceptions, so an
LLM driving this server in a ReAct loop can self-repair its next call.
"""

import os
from typing import Any, Literal, Optional

from mcp.server.fastmcp import FastMCP

from . import discovery
from .client import SensApiError, SensClient
from .formatter import format_price_response, format_tariffs_markdown

mcp = FastMCP("sens-energy")

_client: Optional[SensClient] = None


def get_client() -> SensClient:
    global _client
    if _client is None:
        _client = SensClient()
    return _client


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("sens://market/cheat-sheet")
def market_cheat_sheet() -> str:
    """Polish electricity market cheat sheet: OSDs, tariff groups, price components."""
    return discovery.CHEAT_SHEET_MARKDOWN


# ---------------------------------------------------------------------------
# Discovery tools
# ---------------------------------------------------------------------------


@mcp.tool()
def resolve_operator(query: str, region: Optional[str] = None) -> dict[str, Any]:
    """Resolve a natural-language city or company name to the exact OSD (distribution
    operator) and default retailer strings the SENS API expects.

    Example: query="Kraków" or query="enea". Handles typos via fuzzy matching.
    """
    result = discovery.resolve_operator(query, region=region)
    if result is not None:
        return result

    candidates = discovery.resolve_operator_candidates(query)
    if candidates:
        return {
            "status": "error",
            "error_code": "AMBIGUOUS_OPERATOR",
            "message": (
                f"Operator '{query}' is ambiguous or not an exact match. "
                "SENS separates network distribution (OSD) from energy retail (sprzedawca)."
            ),
            "suggestions": {"did_you_mean": candidates},
            "example_valid_call": f"resolve_operator(query='{candidates[0]}')",
        }

    return {
        "status": "error",
        "error_code": "UNRESOLVABLE_OPERATOR",
        "message": f"Could not resolve '{query}' to any known OSD or retailer.",
        "suggestions": {
            "known_osds": [op.osd for op in discovery.OPERATORS],
        },
        "remediation": "Check sens://market/cheat-sheet for the full list of supported operators.",
    }


@mcp.tool()
def search_tariffs(
    customer_type: Literal["home", "small_business", "industry"],
    zone_preference: Optional[Literal["1-zone", "2-zone-night", "2-zone-weekend", "3-zone"]] = None,
    operator: Optional[str] = None,
) -> dict[str, Any]:
    """Discover valid tariff codes tailored to a customer profile (household,
    small business, or industry), optionally narrowed by zone preference and
    operator.
    """
    if operator is not None:
        resolved = discovery.resolve_operator(operator)
        if resolved is None:
            candidates = discovery.resolve_operator_candidates(operator)
            return {
                "status": "error",
                "error_code": "AMBIGUOUS_OPERATOR",
                "message": f"Operator '{operator}' is ambiguous or not an exact match.",
                "suggestions": {"did_you_mean": candidates} if candidates else None,
                "example_valid_call": "search_tariffs(customer_type='home', operator='TAURON Dystrybucja S.A.')",
            }

    return {"status": "ok", "tariffs": discovery.search_tariffs(customer_type, zone_preference, operator)}


# ---------------------------------------------------------------------------
# Data tools (single source of truth — SENS backend does all calculation)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_prices(
    osd: str,
    taryfa: str,
    sprzedawca: Optional[str] = None,
    date: Optional[str] = None,
    market: Optional[str] = None,
    annual_kwh: Optional[float] = None,
    region: Optional[str] = None,
    since: Optional[str] = None,
    detail_level: Literal["summary", "detailed"] = "summary",
    page: int = 0,
    size: int = 100,
) -> dict[str, Any]:
    """Fetch composite electricity prices and rate breakdown for a given OSD +
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
            osd=osd,
            sprzedawca=sprzedawca,
            taryfa=taryfa,
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

    return {"status": "ok", **format_price_response(payload, detail_level=detail_level)}


@mcp.tool()
async def get_tariff_components(tariff_id: str, since: Optional[str] = None) -> dict[str, Any]:
    """Inspect the detailed fixed/variable rate components of a tariff, as
    approved by URE (the Polish energy regulator).
    """
    client = get_client()
    try:
        payload = await client.get_tariff_components(tariff_id, since=since)
    except SensApiError as e:
        return e.to_dict()

    return {"status": "ok", **payload}


def main() -> None:
    """Synchronous entrypoint used by __main__.py / the `sens-mcp` console script."""
    mcp.run()
