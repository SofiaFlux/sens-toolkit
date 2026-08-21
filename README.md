# sens-mcp

An MCP (Model Context Protocol) server and developer starter kit for the
[SENS Energy Data API](https://api.getsens.energy) — the Polish electricity
market data API (distribution operators, tariffs, and composite price
calculations).

It solves the "cold start" problem for LLMs and AI agents (Claude Desktop,
Cursor, LangChain, n8n, ...) talking to the API: the Polish energy market has
its own vocabulary (OSD vs. sprzedawca, tariff groups `G11`/`G12`/`G12w`/...)
that models don't know out of the box, and raw REST responses are too large
and too easy to miscalculate against by hand.

`sens-mcp` provides:
- **Zero-shot discoverability** — an MCP resource (`sens://market/cheat-sheet`)
  and discovery tools (`resolve_operator`, `search_tariffs`) that teach the
  model the market vocabulary in under ~400 tokens.
- **Actionable self-correction** — tool errors return structured JSON with
  suggestions (`did you mean G12w?`) instead of raw HTTP failures, so an
  agent in a ReAct loop can repair its own next call.
- **Single source of truth calculations** — all price/volume math happens on
  the SENS backend; the toolkit never re-derives totals client-side.
- **Non-blocking startup** — the server boots instantly with an embedded
  fallback market schema; live tariff metadata refreshes in the background.

## Quickstart

### Run via `uvx` (recommended, no install step)

```bash
export SENS_API_KEY=sens_live_your_key_here
uvx sens-mcp
```

### Or install with pip

```bash
pip install sens-mcp
export SENS_API_KEY=sens_live_your_key_here
python -m sens_mcp
```

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SENS_API_KEY` | Yes | — | Your SENS API key. Sent as the `X-API-KEY` header. |
| `SENS_BASE_URL` | No | `https://api.getsens.energy` | Override for staging/self-hosted deployments. |

## Using it with an AI agent

### Claude Desktop

Add to `claude_desktop_config.json` (see [`configs/claude_desktop_config.json`](configs/claude_desktop_config.json)):

```json
{
  "mcpServers": {
    "sens-energy": {
      "command": "uvx",
      "args": ["sens-mcp"],
      "env": {
        "SENS_API_KEY": "sens_live_your_key_here"
      }
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json` (see [`configs/cursor_mcp.json`](configs/cursor_mcp.json)) — same shape as above.

## Tools exposed

| Tool | Purpose |
|---|---|
| `resolve_operator(query, region=None)` | Fuzzy-resolve a city or company name (typo-tolerant) to the exact `osd`/`sprzedawca` strings the API expects. |
| `search_tariffs(customer_type, zone_preference=None, operator=None)` | Discover valid tariff codes for a customer profile (home / small business / industry). |
| `get_prices(osd, taryfa, ...)` | Fetch composite electricity prices and rate breakdown; pass `annual_kwh` for exact volume-weighted totals. |
| `get_tariff_components(tariff_id)` | Inspect a tariff's URE-approved fixed/variable rate components. |

Resource: `sens://market/cheat-sheet` — a Markdown cheat sheet of Polish
electricity market vocabulary (OSDs, tariff groups, price component
structure).

## Developer examples (no MCP required)

Standalone snippets that hit the SENS REST API directly:

- [`examples/python/get_prices.py`](examples/python/get_prices.py)
- [`examples/python/list_tariffs.py`](examples/python/list_tariffs.py)
- [`examples/python/async_stream.py`](examples/python/async_stream.py) — delta sync via `since`
- [`examples/typescript/get_prices.ts`](examples/typescript/get_prices.ts)
- [`examples/curl/api_requests.sh`](examples/curl/api_requests.sh)

## API reference (essentials)

- Base URL: `https://api.getsens.energy`
- Auth: `X-API-KEY: <your key>` header (not Bearer, not a query param).
- `GET /api/v1/prices` — `osd`, `sprzedawca`, `taryfa`, `market`, `date`,
  `annual_kwh`, `region`, `since`, `page`, `size` (max 1000).
- `GET /api/v1/tariffs` — `since`/`If-Modified-Since` for delta queries,
  `page`, `size`.
- `GET /api/v1/tariffs/components?tariff_id=...` — component breakdown for a
  single tariff, also supports `since`.

Full Swagger/OpenAPI docs: `https://api.getsens.energy/api/docs`.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Tests mock all HTTP calls with [`respx`](https://lundberg.github.io/respx/) —
nothing in the default test suite hits the live API.

### Live integration suite (opt-in)

`tests/test_live_integration.py` runs the real server as a subprocess over
the real MCP stdio protocol against the real production SENS API, and checks
byte-for-byte parity between MCP tool responses and raw `httpx` calls to the
same endpoints. Excluded by default; run explicitly with a real key:

```bash
SENS_API_KEY=<a real key> pytest -m live tests/test_live_integration.py -v
```

## License

MIT
