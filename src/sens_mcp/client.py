"""Async HTTP client for the SENS Energy Data API.

Implements the non-blocking lazy initialization strategy from design spec
§5: the server boots instantly using the embedded fallback schema in
`discovery.py`, and this client refreshes live tariff/operator metadata in the
background on the first real tool call rather than blocking startup.

Also centralizes structured-error mapping for real HTTP failures
(401/403/timeout/5xx) so raw httpx exceptions never reach the MCP client.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.getsens.energy"


class SensApiError(Exception):
    """Raised for any SENS API failure; carries a structured error payload."""

    def __init__(self, error_code: str, message: str, remediation: str | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.remediation = remediation

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "status": "error",
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.remediation:
            d["remediation"] = self.remediation
        return d


class SensClient:
    """Thin async wrapper around httpx with background metadata caching."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 15.0):
        self.base_url = base_url or os.environ.get("SENS_BASE_URL", DEFAULT_BASE_URL)
        self.api_key = api_key if api_key is not None else os.environ.get("SENS_API_KEY")
        self.timeout = timeout

        self._client: httpx.AsyncClient | None = None
        self._metadata_task: asyncio.Task | None = None
        self._known_tariff_codes: list[str] | None = None
        self._known_osd_names: list[str] | None = None
        self._metadata_lock = asyncio.Lock()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "X-Client-Type": "mcp"}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        return headers

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self._client

    async def aclose(self) -> None:
        if self._metadata_task is not None and not self._metadata_task.done():
            self._metadata_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._metadata_task
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def start_background_refresh(self) -> None:
        """Kick off a non-blocking background metadata refresh.

        Safe to call from a sync context (e.g. server startup) as long as an
        event loop is already running; it schedules a task and returns
        immediately without awaiting it.
        """
        if self._metadata_task is None or self._metadata_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._metadata_task = loop.create_task(self._refresh_metadata())
            except RuntimeError:
                # No running loop (e.g. import-time call outside async context);
                # metadata will lazily refresh on first real tool call instead.
                pass

    async def ensure_metadata(self) -> None:
        """Ensure a metadata refresh has been attempted at least once, without blocking startup.

        Called lazily on the first real tool invocation per design spec §5.
        """
        if self._known_tariff_codes is not None:
            return
        async with self._metadata_lock:
            if self._known_tariff_codes is not None:
                return
            if self._metadata_task is not None and not self._metadata_task.done():
                # A background refresh (start_background_refresh) is already
                # in flight — await it instead of firing a duplicate request.
                with contextlib.suppress(Exception):
                    await self._metadata_task
                return
            await self._refresh_metadata()

    async def _refresh_metadata(self) -> None:
        try:
            data = await self._request("GET", "/api/v1/tariffs", params={"size": 1000, "page": 0})
            # The public SENS collection envelope is `data`; keep the older
            # `items`/`content` aliases for compatibility with pre-release and
            # mocked responses instead of silently treating live metadata as empty.
            items = data.get("data") or data.get("items") or data.get("content") or []
            codes = sorted({row.get("tariff_code") for row in items if isinstance(row, dict) and row.get("tariff_code")})
            osd_names = sorted(
                {
                    row.get("operator_name").strip()
                    for row in items
                    if isinstance(row, dict)
                    and isinstance(row.get("operator_name"), str)
                    and row.get("operator_name").strip()
                    and str(row.get("operator_type", "")).upper() == "OSD"
                },
                key=str.casefold,
            )
            self._known_tariff_codes = codes
            self._known_osd_names = osd_names
        except Exception:  # noqa: BLE001, S110 - deliberately broad and silent, see comment below
            # Background refresh failures must never surface as a hard error —
            # discovery.py's embedded fallback schema keeps working either way.
            # Leave metadata as None so a later call can retry rather than
            # permanently caching the failure as "loaded empty".
            pass

    @property
    def known_tariff_codes(self) -> list[str]:
        return self._known_tariff_codes or []

    @property
    def known_osd_names(self) -> list[str]:
        return self._known_osd_names or []

    async def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        client = self._ensure_client()
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            resp = await client.request(method, path, params=clean_params, headers=self._headers())
        except httpx.TimeoutException as e:
            raise SensApiError(
                "UPSTREAM_TIMEOUT",
                f"The SENS API did not respond in time: {e}",
                remediation="Retry the request; if it persists, check https://api.getsens.energy status.",
            ) from e
        except httpx.RequestError as e:
            raise SensApiError(
                "UPSTREAM_UNREACHABLE",
                f"Could not reach the SENS API: {e}",
                remediation="Check network connectivity and the SENS_BASE_URL environment variable.",
            ) from e

        if resp.status_code in (401, 403):
            raise SensApiError(
                "UNAUTHORIZED",
                "Missing or invalid SENS API key.",
                remediation="Please configure SENS_API_KEY environment variable in your Claude Desktop or Cursor MCP settings.",
            )
        if resp.status_code == 404:
            raise SensApiError(
                "NOT_FOUND",
                f"The requested resource was not found: {path}",
                remediation="Double check the identifier (e.g. tariff_id) and retry.",
            )
        if resp.status_code == 429:
            raise SensApiError(
                "RATE_LIMITED",
                "The SENS API rate limit was exceeded.",
                remediation="Wait a moment and retry with fewer/less frequent requests.",
            )
        if resp.status_code >= 500:
            raise SensApiError(
                "UPSTREAM_ERROR",
                f"The SENS API returned a server error (HTTP {resp.status_code}).",
                remediation="This is likely transient; retry shortly.",
            )
        if resp.status_code >= 400:
            raise SensApiError(
                "BAD_REQUEST",
                f"The SENS API rejected the request (HTTP {resp.status_code}): {resp.text[:500]}",
                remediation="Check the parameter values (dso, tariff, retailer, etc.) against sens://market/cheat-sheet.",
            )

        if resp.status_code == 304 or not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError as e:
            raise SensApiError(
                "INVALID_RESPONSE",
                f"The SENS API returned a non-JSON response: {e}",
            ) from e

    async def get_prices(
        self,
        dso: str | None = None,
        retailer: str | None = None,
        tariff: str | None = None,
        market: str | None = None,
        date: str | None = None,
        annual_kwh: int | None = None,
        region: str | None = None,
        since: str | None = None,
        page: int = 0,
        size: int = 100,
    ) -> dict[str, Any]:
        await self.ensure_metadata()
        return await self._request(
            "GET",
            "/api/v1/prices",
            params={
                "dso": dso,
                "retailer": retailer,
                "tariff": tariff,
                "market": market,
                "date": date,
                "annual_kwh": annual_kwh,
                "region": region,
                "since": since,
                "page": page,
                "size": size,
            },
        )

    async def get_tariffs(
        self,
        since: str | None = None,
        page: int = 0,
        size: int = 100,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/v1/tariffs",
            params={"since": since, "page": page, "size": size},
        )

    async def tariff_exists(self, tariff_id: str) -> bool:
        """Return whether a tariff id is present in the public catalog.

        The components endpoint is a collection filter and legitimately returns
        an empty list both for an unknown tariff id and for a known tariff with
        no component rows. Only the rare empty-components path needs this
        catalog walk; normal component lookups incur no extra request.
        """
        page = 0
        page_size = 1000
        while True:
            payload = await self.get_tariffs(page=page, size=page_size)
            rows = payload.get("data") or payload.get("items") or payload.get("content") or []
            if not isinstance(rows, list):
                raise SensApiError(
                    "INVALID_RESPONSE",
                    "The SENS tariff catalog returned a non-list collection.",
                    remediation="Retry the request; if it persists, report a backend schema mismatch.",
                )
            if any(isinstance(row, dict) and row.get("tariff_id") == tariff_id for row in rows):
                return True

            total = payload.get("total")
            if isinstance(total, (int, float)) and not isinstance(total, bool):
                if (page + 1) * page_size >= int(total):
                    return False
            elif len(rows) < page_size:
                return False

            # A full page with no trustworthy total means another page may
            # exist. Bound the walk so a malformed upstream envelope cannot
            # create an infinite MCP call.
            page += 1
            if page >= 10_000:
                raise SensApiError(
                    "INVALID_RESPONSE",
                    "The SENS tariff catalog pagination did not terminate.",
                    remediation="Retry the request; if it persists, report the catalog pagination issue.",
                )

    async def get_tariff_components(self, tariff_id: str, since: str | None = None) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/v1/tariffs/components",
            params={"tariff_id": tariff_id, "since": since},
        )
