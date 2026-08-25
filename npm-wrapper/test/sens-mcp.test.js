"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const childProcess = require("node:child_process");
const { hasUvx } = require("../bin/sens-mcp.js");

test("hasUvx returns true when `uvx --version` exits 0", (t) => {
  t.mock.method(childProcess, "spawnSync", () => ({ status: 0 }));
  assert.equal(hasUvx(), true);
});

test("hasUvx returns false when uvx is not on PATH (ENOENT)", (t) => {
  t.mock.method(childProcess, "spawnSync", () => ({
    error: new Error("spawnSync uvx ENOENT"),
    status: null,
  }));
  assert.equal(hasUvx(), false);
});

test("hasUvx returns false when uvx exits non-zero", (t) => {
  t.mock.method(childProcess, "spawnSync", () => ({ status: 1 }));
  assert.equal(hasUvx(), false);
});
