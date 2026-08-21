"""Fetch composite electricity prices from the SENS API directly (no MCP).

Usage:
    export SENS_API_KEY=sens_live_your_key_here
    python get_prices.py
"""

from __future__ import annotations

import os

import httpx

BASE_URL = os.environ.get("SENS_BASE_URL", "https://api.getsens.energy")
API_KEY = os.environ["SENS_API_KEY"]


def main() -> None:
    resp = httpx.get(
        f"{BASE_URL}/api/v1/prices",
        params={
            "osd": "TAURON Dystrybucja S.A.",
            "taryfa": "G12w",
            "annual_kwh": 3000,
        },
        headers={"X-API-KEY": API_KEY},
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()

    print(f"mode: {data['meta']['mode']}")
    for offer in data.get("offers", []):
        summary = offer.get("summary", {})
        print(f"  {offer['tariff_code']}: avg {summary.get('total_avg_pln_per_kwh')} PLN/kWh")


if __name__ == "__main__":
    main()
