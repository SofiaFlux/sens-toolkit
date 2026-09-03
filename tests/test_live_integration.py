"""Live integration suite — exercises the real sens-mcp server subprocess over
the actual MCP stdio protocol against the real production SENS API.

Unlike every other test module (all respx-mocked, zero network), this proves
the thing the mocked suite structurally cannot: that the MCP protocol layer,
the real HTTP client, and the real SENS API agree end-to-end, and that an
MCP client (Claude, or anything speaking MCP) can do everything a raw curl/
httpx call can do — with the added value of discovery/self-correction on top.

Skipped by default. Requires:
    SENS_API_KEY=<a real, active API key>   pytest tests/test_live_integration.py -v -m live

Never run as part of the default `pytest` invocation (see pyproject.toml's
`markers`/`addopts` — `live` tests are deselected unless explicitly requested)
so CI/local dev never depends on network access or a live key.

Each test opens its own stdio subprocess/session rather than sharing one via
a fixture: `stdio_client`'s anyio TaskGroup must be entered and exited within
the same asyncio Task, which a yield-based pytest fixture cannot guarantee
across pytest-asyncio's per-test task boundaries. A few extra subprocess
spins are a fine trade for a suite that isn't flaky.
"""

from __future__ import annotations

import contextlib
import json
import os

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SENS_API_KEY = os.environ.get("SENS_API_KEY", "")
SENS_BASE_URL = os.environ.get("SENS_BASE_URL", "https://api.getsens.energy")
SENS_MCP_ENTRYPOINT = os.environ.get("SENS_MCP_ENTRYPOINT", "sens-mcp")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not SENS_API_KEY, reason="SENS_API_KEY not set — skipping live integration tests"),
]


def _server_params(api_key: str = SENS_API_KEY) -> StdioServerParameters:
    return StdioServerParameters(
        command=SENS_MCP_ENTRYPOINT,
        args=[],
        env={**os.environ, "SENS_API_KEY": api_key, "SENS_BASE_URL": SENS_BASE_URL},
    )


@contextlib.asynccontextmanager
async def open_session(api_key: str = SENS_API_KEY):
    async with (
        stdio_client(_server_params(api_key)) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


async def _call(session: ClientSession, tool: str, **kwargs):
    result = await session.call_tool(tool, arguments=kwargs)
    assert not result.isError, f"{tool}({kwargs}) returned an MCP-level error: {result}"
    # FastMCP tools return a single text content block containing JSON.
    return json.loads(result.content[0].text)


class TestProtocolSurface:
    """Proves the server actually speaks MCP correctly, not just 'the Python
    functions work' — this is what an external MCP client (Claude Desktop,
    Cursor, a from-scratch agent) actually sees on connect.
    """

    async def test_lists_all_four_tools(self):
        async with open_session() as session:
            tools = (await session.list_tools()).tools
            names = {t.name for t in tools}
            assert names == {"resolve_operator", "search_tariffs", "get_prices", "get_tariff_components"}

    async def test_lists_cheat_sheet_resource(self):
        async with open_session() as session:
            resources = (await session.list_resources()).resources
            uris = {str(r.uri) for r in resources}
            assert "sens://market/cheat-sheet" in uris

    async def test_reads_cheat_sheet_resource(self):
        async with open_session() as session:
            result = await session.read_resource("sens://market/cheat-sheet")
            content = result.contents[0]
            assert content.mimeType == "text/markdown"
            # Under the spec's ~350-token budget by a wide margin — regression guard
            # against the cheat sheet accidentally growing into a context hog.
            assert len(content.text) < 4000
            assert "G11" in content.text and "TAURON" in content.text


class TestDiscoveryToolsLive:
    async def test_resolve_operator_exact_city(self):
        async with open_session() as session:
            result = await _call(session, "resolve_operator", query="Kraków")
            assert result["osd"] == "TAURON Dystrybucja S.A."
            assert "default_retailer" in result

    async def test_resolve_operator_ambiguous_prefix(self):
        """Regression test for the exact bug the code review caught: 'ene' must
        not silently resolve to Enea just because it's declared first — it's an
        equally valid substring of Energa-Operator too.
        """
        async with open_session() as session:
            result = await _call(session, "resolve_operator", query="ene")
            assert result["status"] == "error"
            assert result["error_code"] == "AMBIGUOUS_OPERATOR"
            candidates = result["suggestions"]["did_you_mean"]
            assert any("Enea" in c for c in candidates)
            assert any("Energa" in c for c in candidates)

    async def test_resolve_operator_unresolvable(self):
        async with open_session() as session:
            result = await _call(session, "resolve_operator", query="xqzwv-frobnicate-qqqjjj")
            assert result["status"] == "error"
            assert result["error_code"] == "UNRESOLVABLE_OPERATOR"
            assert result["suggestions"] is not None  # full known_osds list, not None

    async def test_search_tariffs_home_weekend(self):
        async with open_session() as session:
            result = await _call(session, "search_tariffs", customer_type="home", zone_preference="2-zone-weekend")
            assert result["status"] == "ok"
            codes = {t["code"] for t in result["tariffs"]}
            assert codes == {"G12w"}

    async def test_all_default_retailers_exist_in_tariff_database(self):
        """Validate that each operator's suggested default_retailer (when not None)
        is an actual retailer name recognized by the live API. This prevents the
        compass pointing to a destination that doesn't exist.
        """
        from sens_mcp.discovery import OPERATORS

        async with open_session() as session:
            # For each operator with a non-None default_retailer, try to use it
            # in a get_prices call with a G11 tariff (universally available).
            for op in OPERATORS:
                if op.default_retailer is not None:
                    result = await _call(
                        session,
                        "get_prices",
                        osd=op.osd,
                        taryfa="G11",
                        sprzedawca=op.default_retailer,
                    )
                    # Either the call succeeds with ok status, or it fails due to
                    # lack of coverage for that operator/retailer/tariff combo
                    # (which is acceptable — the retailer name is valid), but NOT
                    # due to the retailer not existing in the database.
                    assert result["status"] != "error" or result.get("error_code") not in {
                        "INVALID_RETAILER",
                        "RETAILER_NOT_FOUND",
                    }, f"Operator {op.osd} has invalid default_retailer: {op.default_retailer}"


class TestDataToolsLiveWithParity:
    """The core proof: an MCP tool call and a raw curl/httpx call against the
    identical endpoint must agree on the actual price data — the MCP layer is
    a faithful, non-lossy (in summary mode: intentionally *token-economical*,
    not lossy on the fields it keeps) wrapper, not a second implementation
    that could silently drift from the real API.
    """

    # A real, stable tariff verified present in prod as of 2026-08-21 (ACPRO
    # sp. z o.o. 2 Sp. k., B21). If this ever 404s because the row aged out,
    # replace with any current `operator_name`/`tariff_code` pair from
    # GET /api/v1/tariffs?size=50 (filter for a non-empty operator_name).
    _OSD = "ACPRO sp. z o.o. 2 Sp. k."
    _TARYFA = "B21"
    _TARIFF_ID = "acpro-2_b21_2026"

    async def test_get_prices_matches_raw_api_call(self):
        async with open_session() as session:
            mcp_result = await _call(session, "get_prices", osd=self._OSD, taryfa=self._TARYFA)
        assert mcp_result["status"] == "ok"

        async with httpx.AsyncClient(base_url=SENS_BASE_URL, timeout=15.0) as client:
            raw = await client.get(
                "/api/v1/prices",
                params={"osd": self._OSD, "taryfa": self._TARYFA},
                headers={"X-API-KEY": SENS_API_KEY},
            )
        raw.raise_for_status()
        raw_json = raw.json()

        # Summary mode intentionally strips catalog/supply/distribution/unmatched
        # (token economy) but meta.resolved, offers[].summary and warnings must
        # be byte-identical to the raw API response — that's the actual data,
        # not audit noise.
        assert mcp_result["meta"]["resolved"] == raw_json["meta"]["resolved"]
        assert mcp_result["offers"][0]["summary"] == raw_json["offers"][0]["summary"]
        assert mcp_result["offers"][0]["tariff_code"] == raw_json["offers"][0]["tariff_code"]
        assert mcp_result["offers"][0]["zones"] == raw_json["offers"][0]["zones"]
        assert mcp_result.get("warnings") == raw_json.get("warnings")

        # And prove summary mode actually strips something (else the two modes
        # would be pointless) — the raw API response carries a full `supply`
        # breakdown per offer that summary mode must not echo back.
        assert "supply" not in mcp_result["offers"][0]
        assert "supply" in raw_json["offers"][0]

    async def test_get_prices_detailed_mode_keeps_supply_breakdown(self):
        async with open_session() as session:
            result = await _call(session, "get_prices", osd=self._OSD, taryfa=self._TARYFA, detail_level="detailed")
        assert "supply" in result["offers"][0]

    async def test_get_tariff_components_matches_raw_api_call(self):
        async with open_session() as session:
            mcp_result = await _call(session, "get_tariff_components", tariff_id=self._TARIFF_ID)
        assert mcp_result["status"] == "ok"
        assert mcp_result["total"] >= 1

        async with httpx.AsyncClient(base_url=SENS_BASE_URL, timeout=15.0) as client:
            raw = await client.get(
                "/api/v1/tariffs/components",
                params={"tariff_id": self._TARIFF_ID},
                headers={"X-API-KEY": SENS_API_KEY},
            )
        raw.raise_for_status()
        raw_json = raw.json()

        mcp_names = sorted(row["name"] for row in mcp_result["data"])
        raw_names = sorted(row["name"] for row in raw_json["data"])
        assert mcp_names == raw_names


class TestErrorHandlingLive:
    """Proves the structured self-correction protocol survives a real round
    trip through the real API's real error responses, not just the respx-
    mocked shapes the unit suite constructs.
    """

    async def test_invalid_api_key_maps_to_unauthorized(self):
        async with open_session(api_key="sens_definitely-not-a-real-key") as session:
            result = await _call(session, "get_prices", osd="TAURON Dystrybucja S.A.", taryfa="G11")
        assert result["status"] == "error"
        assert result["error_code"] == "UNAUTHORIZED"
        assert "remediation" in result

    async def test_unknown_tariff_id_maps_gracefully(self):
        async with open_session() as session:
            result = await _call(session, "get_tariff_components", tariff_id="definitely-does-not-exist-12345")
        # Either an empty result set or a structured NOT_FOUND — either is a
        # valid graceful outcome; a raw traceback/protocol error is not.
        if result.get("status") == "error":
            assert result["error_code"] in {"NOT_FOUND", "MALFORMED_RESPONSE"}
        else:
            assert result.get("total", 0) == 0 or result.get("data") == []
