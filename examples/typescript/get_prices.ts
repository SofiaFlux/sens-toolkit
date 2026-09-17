// Fetch composite electricity prices from the SENS API directly (no MCP).
//
// Usage:
//   export SENS_API_KEY=sens_live_your_key_here
//   npx tsx get_prices.ts

const BASE_URL = process.env.SENS_BASE_URL ?? "https://api.getsens.energy";
const API_KEY = process.env.SENS_API_KEY;

if (!API_KEY) {
  throw new Error("Set SENS_API_KEY before running this example.");
}

interface OfferSummary {
  total_avg_pln_per_kwh?: number;
}

interface Offer {
  tariff_code: string;
  summary: OfferSummary;
}

interface PriceResponse {
  meta: { mode: string };
  offers: Offer[];
}

async function main(): Promise<void> {
  const url = new URL(`${BASE_URL}/api/v1/prices`);
  url.searchParams.set("dso", "TAURON Dystrybucja S.A.");
  url.searchParams.set("tariff", "G12w");
  url.searchParams.set("annual_kwh", "3000");

  const res = await fetch(url, { headers: { "X-API-KEY": API_KEY as string } });
  if (!res.ok) {
    throw new Error(`SENS API error: ${res.status} ${await res.text()}`);
  }

  const data = (await res.json()) as PriceResponse;
  console.log(`mode: ${data.meta.mode}`);
  for (const offer of data.offers ?? []) {
    console.log(`  ${offer.tariff_code}: avg ${offer.summary?.total_avg_pln_per_kwh} PLN/kWh`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
