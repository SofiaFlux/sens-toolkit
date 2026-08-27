# @getsens/mcp-server

`npx`-installable wrapper for [`sens-mcp`](https://pypi.org/project/sens-mcp/)
(the real MCP server — a Python package, distributed via `uv`/`pip`).

This package exists only so Node/npm users have a familiar `npx` entry point.
It does not reimplement anything: it checks for `uv` on your `PATH` and then
runs `uvx sens-mcp`, forwarding all arguments and environment variables
(including `SENS_API_KEY`).

## Requirements

- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) installed
  and on your `PATH`. If it isn't, the wrapper prints an install link and
  exits — it does not attempt to install anything on your behalf.

## Usage

```bash
export SENS_API_KEY=sens_live_your_key_here
npx @getsens/mcp-server
```

Or in an MCP client config (e.g. Claude Desktop):

```json
{
  "mcpServers": {
    "sens-energy": {
      "command": "npx",
      "args": ["-y", "@getsens/mcp-server"],
      "env": { "SENS_API_KEY": "sens_live_your_key_here" }
    }
  }
}
```

See the [full documentation](https://docs.getsens.energy) for everything
`sens-mcp` provides (tools, resources, market vocabulary).

## Development

```bash
npm test
```
