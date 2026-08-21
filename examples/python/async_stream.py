"""Async delta-sync example: poll /api/v1/tariffs with `since` to fetch only
rows that changed after a given timestamp — useful for keeping a local cache
warm without re-downloading the full tariff catalog each time.

Usage:
    export SENS_API_KEY=sens_live_your_key_here
    python async_stream.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import httpx

BASE_URL = os.environ.get("SENS_BASE_URL", "https://api.getsens.energy")
API_KEY = os.environ["SENS_API_KEY"]


async def fetch_since(client: httpx.AsyncClient, since: str) -> list[dict]:
    resp = await client.get("/api/v1/tariffs", params={"since": since, "size": 1000})
    resp.raise_for_status()
    data = resp.json()
    return data.get("items", data.get("content", []))


async def main() -> None:
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    async with httpx.AsyncClient(base_url=BASE_URL, headers={"X-API-KEY": API_KEY}, timeout=15.0) as client:
        rows = await fetch_since(client, since)
        print(f"{len(rows)} tariff rows changed since {since}")
        for row in rows[:10]:
            print(f"  {row.get('tariff_code')} updated_at={row.get('updated_at')}")


if __name__ == "__main__":
    asyncio.run(main())
