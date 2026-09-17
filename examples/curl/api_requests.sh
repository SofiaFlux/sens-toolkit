#!/usr/bin/env bash
# cURL examples for the SENS Energy Data API.
#
# Usage:
#   export SENS_API_KEY=sens_live_your_key_here
#   ./api_requests.sh

set -euo pipefail

BASE_URL="${SENS_BASE_URL:-https://api.getsens.energy}"

if [[ -z "${SENS_API_KEY:-}" ]]; then
  echo "Set SENS_API_KEY before running this script." >&2
  exit 1
fi

echo "== Get composite prices for TAURON G12w, 3000 kWh/year =="
curl -sS -H "X-API-KEY: ${SENS_API_KEY}" \
  --get "${BASE_URL}/api/v1/prices" \
  --data-urlencode "dso=TAURON Dystrybucja S.A." \
  --data-urlencode "tariff=G12w" \
  --data-urlencode "annual_kwh=3000" | head -c 2000
echo

echo "== List first page of tariffs =="
curl -sS -H "X-API-KEY: ${SENS_API_KEY}" \
  --get "${BASE_URL}/api/v1/tariffs" \
  --data-urlencode "page=0" \
  --data-urlencode "size=20" | head -c 2000
echo

echo "== Delta-fetch tariffs changed since a date =="
curl -sS -H "X-API-KEY: ${SENS_API_KEY}" \
  --get "${BASE_URL}/api/v1/tariffs" \
  --data-urlencode "since=2026-08-01" | head -c 2000
echo

echo "== Get tariff components for a specific tariff_id =="
curl -sS -H "X-API-KEY: ${SENS_API_KEY}" \
  --get "${BASE_URL}/api/v1/tariffs/components" \
  --data-urlencode "tariff_id=REPLACE_WITH_TARIFF_ID" | head -c 2000
echo
