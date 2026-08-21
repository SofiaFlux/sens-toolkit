"""List tariffs from the SENS API with pagination.

Usage:
    export SENS_API_KEY=sens_live_your_key_here
    python list_tariffs.py
"""

from __future__ import annotations

import os

import httpx

BASE_URL = os.environ.get("SENS_BASE_URL", "https://api.getsens.energy")
API_KEY = os.environ["SENS_API_KEY"]


def main() -> None:
    page = 0
    size = 100
    with httpx.Client(base_url=BASE_URL, headers={"X-API-KEY": API_KEY}, timeout=15.0) as client:
        while True:
            resp = client.get("/api/v1/tariffs", params={"page": page, "size": size})
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", data.get("content", []))
            for row in items:
                print(f"{row.get('tariff_code'):8s} {row.get('operator_name')}")
            if len(items) < size:
                break
            page += 1


if __name__ == "__main__":
    main()
