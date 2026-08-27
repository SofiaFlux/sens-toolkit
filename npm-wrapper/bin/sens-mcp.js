#!/usr/bin/env node
"use strict";

const childProcess = require("node:child_process");

function hasUvx() {
  const check = childProcess.spawnSync("uvx", ["--version"], { stdio: "ignore" });
  return check.error === undefined && check.status === 0;
}

function main() {
  if (!hasUvx()) {
    console.error(
      "sens-mcp needs `uv` (the Python package manager) to run — it wasn't found on your PATH.\n" +
        "Install it from https://docs.astral.sh/uv/getting-started/installation/ and try again."
    );
    process.exit(1);
  }

  const result = childProcess.spawnSync("uvx", ["sens-mcp", ...process.argv.slice(2)], {
    stdio: "inherit",
    env: process.env,
  });

  if (result.error) {
    console.error(`Failed to launch sens-mcp via uvx: ${result.error.message}`);
    process.exit(1);
  }

  process.exit(result.status ?? 1);
}

module.exports = { hasUvx };

if (require.main === module) {
  main();
}
