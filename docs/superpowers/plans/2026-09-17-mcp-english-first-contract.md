# MCP English-First Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `sens-mcp`'s public MCP tool contract (the `get_prices`/`resolve_operator` tool signatures and their JSON response keys, as seen by an LLM caller) English-first — canonical `dso`/`retailer`/`tariff` only, no Polish aliases — matching the now-live `azure_energy-price-api` backend (Phase 1 of `sens_brain/1_Projects/2026-09-14-public-api-english-contract-backlog.md`, ADR-009).

**Architecture:** MCP is *stricter* than the REST backend: the backend still accepts `osd`/`sprzedawca`/`taryfa` as compatibility aliases, but the MCP tool schema exposes only canonical names — no alias arguments at all (per the backlog doc's explicit MCP section). Rename at the two crossing points: (1) the MCP tool's own parameter/response-dict surface (`server.py`, `discovery.py`'s two dict-builder functions), and (2) `models.py`'s `ResolvedParams`, which deserializes the backend's response — the backend already stopped returning `osd`/`sprzedawca`/`taryfa` (Phase 1, deployed, confirmed live), so this model is currently silently stale (extra="allow" hides the breakage but the declared fields are now always `None`). Internal Python identifiers that never cross the MCP wire (the `Operator.osd` dataclass field, `live_osds` parameters, `known_osd_names` property, `seen_osds` locals) stay as-is — same scoping discipline as the Kotlin backend's Phase 1 (internal domain naming is out of scope; only the public tool/response surface is canonical).

**Tech Stack:** Python 3.12+, FastMCP (`mcp.server.fastmcp`), Pydantic v2, httpx, pytest + pytest-asyncio + respx (mocked HTTP), `uv` for dependency/venv management.

**Spec:** `sens_brain/1_Projects/2026-09-14-public-api-english-contract-backlog.md` (MCP section: "MCP should be stricter than raw REST... Do NOT expose separate MCP arguments for osd, sprzedawca or taryfa"), `sens_brain/4_ADR/SENS_ADR_009_EnglishFirstPublicApiBoundary_2026-09-15.md`.

## Global Constraints

- The `get_prices` and `resolve_operator` MCP tools must accept/return **only** `dso`/`retailer`/`tariff` — no `osd`/`sprzedawca`/`taryfa` parameter or response key anywhere in the public tool contract.
- Do **not** rename internal-only Python identifiers that never appear in a tool's parameter list or JSON response: `Operator.osd` (dataclass field), `OPERATORS` tuple, `live_osds`/`live_osd_names` parameters, `known_osd_names` client property, `_ALIAS_INDEX`, `seen_osds`/`fuzzy_seen` locals, `_OSD`/`_TARYFA` test constants. These are internal domain vocabulary, same as the Kotlin backend's internal `osd`/`sprzedawca` fields staying unchanged in Phase 1.
- `discovery.py`'s natural-language prose (docstrings, the `CHEAT_SHEET_MARKDOWN` resource, error messages) MAY continue to mention "OSD" as the Polish-market synonym for DSO — the spec explicitly allows this ("Natural-language descriptions may still explain that Polish sources/users may call a DSO an OSD"). Lead with DSO, keep OSD as a parenthetical/explanatory mention, matching the Kotlin `@Operation` description pattern from Phase 1.
- The backend (`azure_energy-price-api`) is confirmed live in production with the Phase 1 contract already deployed (`api.getsens.energy`, build 695) — this plan can safely assume `dso`/`retailer`/`tariff` work end-to-end against the real API.
- Test command (mocked suite, default, no network/API key needed): `uv run pytest` from the repo root, or `.venv/bin/pytest`. The `live` suite (`tests/test_live_integration.py`) is excluded by default (`addopts = "-m 'not live'"`) and needs `SENS_API_KEY` — update it for correctness but do not attempt to run it in this plan.

---

## Task 1: Rename the MCP tool contract — source files

**Files:**
- Modify: `src/sens_mcp/models.py`
- Modify: `src/sens_mcp/client.py`
- Modify: `src/sens_mcp/server.py`
- Modify: `src/sens_mcp/discovery.py`
- Test: `tests/test_discovery.py`, `tests/test_server_tools.py`, `tests/test_qa006_region_constraint.py`, `tests/test_qa031_live_operator_resolution.py`, `tests/test_qa032_market_parity.py`

**Interfaces:**
- Produces: `get_prices(dso: str, tariff: str, retailer: str | None = None, ...)` (was `osd`/`taryfa`/`sprzedawca`) as the MCP tool signature in `server.py`; `SensClient.get_prices(dso=..., retailer=..., tariff=..., ...)` sends `{"dso": ..., "retailer": ..., "tariff": ...}` as REST query params (canonical, not the alias names — the backend accepts either, MCP always sends canonical); `resolve_operator(...)` and its error paths return `{"dso": ..., "default_retailer": ..., "region": ..., "supported_tariff_groups": ...}` (was `"osd"`) and `{"suggestions": {"known_dsos": [...]}}` (was `"known_osds"`); `ResolvedParams` has fields `dso`, `retailer`, `market`, `tariff` (was `osd`, `sprzedawca`, `market`, `taryfa`).

This task changes 4 source files and 5 test files together (renaming a contract across its only call sites/consumers is not meaningfully splittable into two green states — same reasoning as the Kotlin backend's Task 3).

- [ ] **Step 1: Update `models.py`'s `ResolvedParams`**

In `src/sens_mcp/models.py`, replace:

```python
class ResolvedParams(SensModel):
    osd: str | None = None
    sprzedawca: str | None = None
    market: str | None = None
    taryfa: str | None = None
```

with:

```python
class ResolvedParams(SensModel):
    dso: str | None = None
    retailer: str | None = None
    market: str | None = None
    tariff: str | None = None
```

- [ ] **Step 2: Update `client.py`'s `get_prices` method**

In `src/sens_mcp/client.py`, replace the `get_prices` method (currently around line 207):

```python
    async def get_prices(
        self,
        osd: str | None = None,
        sprzedawca: str | None = None,
        taryfa: str | None = None,
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
                "osd": osd,
                "sprzedawca": sprzedawca,
                "taryfa": taryfa,
                "market": market,
                "date": date,
                "annual_kwh": annual_kwh,
                "region": region,
                "since": since,
                "page": page,
                "size": size,
            },
        )
```

with:

```python
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
```

Also update the docstring/comment on line ~194 that lists parameter names in the remediation string:

```python
                remediation="Check the parameter values (osd, taryfa, sprzedawca, etc.) against sens://market/cheat-sheet.",
```

to:

```python
                remediation="Check the parameter values (dso, tariff, retailer, etc.) against sens://market/cheat-sheet.",
```

- [ ] **Step 3: Update `discovery.py`'s two dict-builder functions**

In `src/sens_mcp/discovery.py`, `_live_osd_to_dict` (currently around line 219):

```python
def _live_osd_to_dict(osd: str) -> dict:
    """Return the common resolver shape without inventing unavailable metadata."""
    return {
        "osd": osd,
        "default_retailer": None,
        "region": None,
        "supported_tariff_groups": [],
    }
```

Change only the dict key (the function name and parameter name stay — internal identifiers):

```python
def _live_osd_to_dict(osd: str) -> dict:
    """Return the common resolver shape without inventing unavailable metadata."""
    return {
        "dso": osd,
        "default_retailer": None,
        "region": None,
        "supported_tariff_groups": [],
    }
```

`_operator_to_dict` (currently around line 382):

```python
def _operator_to_dict(op: Operator) -> dict:
    return {
        "osd": op.osd,
        "default_retailer": op.default_retailer,
        "region": op.region,
        "supported_tariff_groups": list(op.supported_tariff_groups),
    }
```

becomes:

```python
def _operator_to_dict(op: Operator) -> dict:
    return {
        "dso": op.osd,
        "default_retailer": op.default_retailer,
        "region": op.region,
        "supported_tariff_groups": list(op.supported_tariff_groups),
    }
```

(`op.osd` — the internal dataclass field access — is unchanged; only the dict key on the left changes.)

- [ ] **Step 4: Update `server.py`'s MCP tool signatures and response-dict keys**

In `src/sens_mcp/server.py`:

1. `_operator_resolution_error` (currently around line 44-75) — rename the `known_osds` key in its returned dict (the local variable name may stay, only the dict key matters, but renaming both keeps the function readable — your call on the local variable, the dict key is mandatory):

```python
    known_osds = [op.osd for op in discovery.OPERATORS]
    for osd in live_osds or []:
        if osd not in known_osds:
            known_osds.append(osd)
    return {
        "status": "error",
        "error_code": "UNRESOLVABLE_OPERATOR",
        "message": f"Could not resolve '{query}' to any known OSD or retailer.",
        "suggestions": {
            "known_osds": known_osds,
        },
        "remediation": "Check sens://market/cheat-sheet or the live tariff catalog for supported operators.",
    }
```

The `"suggestions": {"known_osds": known_osds}` line becomes `"suggestions": {"known_dsos": known_osds}`. Everything else in that function (the `known_osds` local variable name, the `live_osds` parameter, the "OSD" text in the `message` string) stays as-is — the message string may keep saying "OSD" per the Global Constraints' natural-language allowance.

2. `resolve_operator` tool (currently around line 95-138) — the `REGION_MISMATCH` error branch reads `unconstrained['osd']` twice (lines ~121, 125). Since `_operator_to_dict`/`_live_osd_to_dict` (Step 3) now produce a `"dso"` key, not `"osd"`, update both reads:

```python
                    f"'{query}' resolves to {unconstrained['osd']} in region "
                    f"'{actual_region}', which conflicts with requested region '{region}'."
                ),
                "suggestions": {
                    "resolved_operator": unconstrained["osd"],
```

becomes:

```python
                    f"'{query}' resolves to {unconstrained['dso']} in region "
                    f"'{actual_region}', which conflicts with requested region '{region}'."
                ),
                "suggestions": {
                    "resolved_operator": unconstrained["dso"],
```

3. `get_prices` tool (currently around line 178-222) — rename the signature and the call into `client.get_prices`:

```python
@mcp.tool()
async def get_prices(
    osd: str,
    taryfa: str,
    sprzedawca: str | None = None,
    date: str | None = None,
    market: str | None = None,
    annual_kwh: int | None = None,
    region: str | None = None,
    since: str | None = None,
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
```

becomes:

```python
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
```

4. `resolve_operator` tool's docstring (currently around line 96-97) says:

```python
    """Resolve a natural-language city or company name to the exact OSD (distribution
    operator) and default retailer strings the SENS API expects.
```

Update to lead with DSO, per the Global Constraints' "lead with DSO, OSD as parenthetical" rule:

```python
    """Resolve a natural-language city or company name to the exact DSO (distribution
    operator, sometimes called OSD in Polish-market sources) and default retailer
    strings the SENS API expects.
```

- [ ] **Step 5: Update the mocked test files**

In each file below, change every `osd=`/`taryfa=`/`sprzedawca=` keyword argument passed to `server.get_prices(...)` or `discovery.resolve_operator(...)` to `dso=`/`tariff=`/`retailer=`, and every `result["osd"]`/`"known_osds"` assertion to `result["dso"]`/`"known_dsos"`, and every mocked backend JSON fixture's `"resolved": {"osd": ..., "taryfa": ...}` to `"resolved": {"dso": ..., "tariff": ...}`. Locate every occurrence with:

```bash
grep -n '"osd"\|osd=\|taryfa=\|sprzedawca=\|"taryfa"\|"sprzedawca"\|known_osds' tests/test_discovery.py tests/test_server_tools.py tests/test_qa006_region_constraint.py tests/test_qa031_live_operator_resolution.py tests/test_qa032_market_parity.py
```

Apply the same mechanical substitution at each hit. Do **not** touch `op.osd` (the `Operator` dataclass field access — stays `osd`), `live_osds`/`live_osd_names` parameters/locals, or comments/docstrings unrelated to the MCP wire contract (e.g. `test_discovery.py`'s Polish-language comment at line 111 mentioning `sprzedawca` as prose, if it's explaining behavior rather than asserting a dict key — use judgment, the grep above will show you each one in context).

- [ ] **Step 6: Run the full mocked suite and fix any remaining fallout**

Run: `uv run pytest` (from `/home/topol/git/sens-toolkit`)

Fix any compile/import errors or assertion failures the same way — mechanical rename of `osd`/`sprzedawca`/`taryfa` wire-contract references. Do not skip actually running the suite to confirm.

Expected: PASS, full suite green (the `live` marker is excluded by default per `addopts`, so this run needs no network/API key).

- [ ] **Step 7: Commit**

```bash
git add src/sens_mcp/models.py src/sens_mcp/client.py src/sens_mcp/server.py src/sens_mcp/discovery.py tests/test_discovery.py tests/test_server_tools.py tests/test_qa006_region_constraint.py tests/test_qa031_live_operator_resolution.py tests/test_qa032_market_parity.py
git commit -m "feat(mcp): expose only canonical dso/retailer/tariff in the MCP tool contract"
```

---

## Task 2: Update the live-integration test and add a regression lock

**Files:**
- Modify: `tests/test_live_integration.py`
- Modify: `tests/test_server_tools.py`

**Interfaces:**
- Consumes: the Task 1 MCP tool contract (`get_prices(dso=, tariff=, retailer=)`, `resolve_operator` returning `"dso"`).

- [ ] **Step 1: Update `test_live_integration.py`'s MCP/REST calls to canonical params**

This suite is excluded by default (`-m 'not live'`) and cannot be run in this environment without `SENS_API_KEY` — update it for correctness by reading, not by running.

Locate every `osd=`/`taryfa=`/`sprzedawca=` usage:

```bash
grep -n 'osd=\|taryfa=\|sprzedawca=\|"osd"\|"taryfa"\|_OSD\|_TARYFA\|known_osds' tests/test_live_integration.py
```

For each MCP tool call (`_call(session, "get_prices", osd=..., taryfa=...)`) and each raw `params={"osd": ..., "taryfa": ...}` REST call, rename to `dso=`/`tariff=` (and `params={"dso": ..., "tariff": ...}`). For each `result["osd"]` assertion (checking the `resolve_operator` tool's response), rename to `result["dso"]`. The `_OSD`/`_TARYFA` class constants and `op.osd` accesses are internal test fixtures, not part of the wire contract — you may rename them for consistency with the rest of the file if it reads better, but it is not required; use your judgment and note which you chose in your report.

- [ ] **Step 2: Add a regression-lock test to `test_server_tools.py`**

Append a test that asserts `get_prices` and `resolve_operator`'s responses never contain the legacy `osd`/`sprzedawca`/`taryfa` keys. Follow this file's existing patterns for mocking the backend (check how the existing tests around line 27, 50 mock the HTTP response via `respx`) and write two assertions in that style: one for `get_prices` (mock a backend response containing `"resolved": {"dso": "...", "tariff": "..."}`, call `server.get_prices(dso=..., tariff=...)`, assert the result's `resolved` dict has no `osd`/`sprzedawca`/`taryfa` keys), and one for `resolve_operator` (call it with a known operator name, assert the result dict has no `osd` key and does have a `dso` key).

- [ ] **Step 3: Run the full mocked suite**

Run: `uv run pytest`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_live_integration.py tests/test_server_tools.py
git commit -m "test(mcp): lock canonical-only dso/retailer/tariff in MCP responses, update live suite"
```

---

## Self-Review Notes (for whoever executes this plan)

- **Spec coverage:** MCP tool signature (Task 1 Steps 3-4), response dict keys (Task 1 Steps 3-4), client REST call params sent as canonical (Task 1 Step 2), stale `ResolvedParams` model fixed (Task 1 Step 1), regression lock (Task 2 Step 2), live-suite consistency (Task 2 Step 1) — all covered.
- **Deliberately NOT covered here**: `sens-docs` (Phase 3, separate repo/plan), any change to `discovery.py`'s internal `Operator`/`OPERATORS`/alias-matching logic beyond the two dict-builder functions' output keys, the `CHEAT_SHEET_MARKDOWN` resource's prose (may still say "OSD" per the spec's natural-language allowance).
- **Deploy note**: `sens-mcp` is a client the AI/LLM caller runs directly (via `npm-wrapper`/console script), not a server Adam deploys to Azure — there's no separate "prod rollout" step the way Phase 1 had. Once this merges and a new version is published/installed, callers get the new tool signature immediately. Confirm with Adam whether `sens-mcp` has a version bump / publish step (check `pyproject.toml`'s `version` field and `npm-wrapper/`) that should accompany this change.
