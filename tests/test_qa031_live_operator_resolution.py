import httpx
import respx

from sens_mcp import discovery, server
from sens_mcp.client import SensClient


POLENERGIA_RAW = "POLENERGIA Dystrybucja Sp. z o. o."
POLENERGIA_CANONICAL = "POLENERGIA Dystrybucja Sp. z o.o."
LIVE_LOOKALIKE = "EneaX Operator Sp. z o.o."


def test_qa031_unknown_polenergia_never_guesses_an_embedded_operator():
    """Without live metadata, a missing OSD is safer as unresolved than as the
    wrong company. In particular POLENERGIA must never fuzzy-resolve to Energa.
    """
    assert discovery.resolve_operator("polenergia") is None
    assert discovery.resolve_operator(POLENERGIA_CANONICAL) is None


def test_qa031_discovery_resolves_legal_form_variant_from_live_catalog():
    """A source-faithful `o. o.` spelling must still be discoverable from the
    conventional `o.o.` spelling when the operator comes from live metadata.
    """
    result = discovery.resolve_operator(
        POLENERGIA_CANONICAL,
        live_osds=[POLENERGIA_RAW],
    )

    assert result is not None
    assert result["osd"] == POLENERGIA_RAW


def test_qa031_live_direct_match_outranks_embedded_fuzzy_alias():
    """A real live-catalog entity must beat a merely similar embedded alias."""
    result = discovery.resolve_operator("eneax", live_osds=[LIVE_LOOKALIKE])

    assert result is not None
    assert result["osd"] == LIVE_LOOKALIKE


@respx.mock
async def test_qa031_metadata_retains_live_osd_names():
    """The metadata refresh must not discard operator names from /tariffs."""
    client = SensClient(base_url="https://api.getsens.energy", api_key="k")
    respx.get("https://api.getsens.energy/api/v1/tariffs").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "tariff_code": "G11",
                        "operator_name": POLENERGIA_RAW,
                        "operator_type": "OSD",
                    },
                    {
                        "tariff_code": "G11",
                        "operator_name": "POLENERGIA Sprzedaż Sp. z o.o.",
                        "operator_type": "RETAILER",
                    },
                ]
            },
        )
    )

    await client.ensure_metadata()

    assert client.known_osd_names == [POLENERGIA_RAW]
    await client.aclose()


async def test_qa031_mcp_resolve_operator_falls_back_to_live_catalog(monkeypatch):
    """The MCP resolver must cover OSDs outside the five embedded fallbacks."""

    class FakeClient:
        known_osd_names = [POLENERGIA_RAW]

        async def ensure_metadata(self):
            return None

    monkeypatch.setattr(server, "get_client", lambda: FakeClient())

    result = await server.resolve_operator("polenergia")

    assert result["osd"] == POLENERGIA_RAW
    assert result["default_retailer"] is None


async def test_qa031_mcp_live_direct_match_outranks_embedded_fuzzy_alias(monkeypatch):
    class FakeClient:
        known_osd_names = [LIVE_LOOKALIKE]

        async def ensure_metadata(self):
            return None

    monkeypatch.setattr(server, "get_client", lambda: FakeClient())

    result = await server.resolve_operator("eneax")

    assert result["osd"] == LIVE_LOOKALIKE
