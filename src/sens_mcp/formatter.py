"""Token-efficient Markdown & compact JSON formatters.

`detail_level="summary"` (the default for `get_prices`) strips verbose/audit
fields before the response is handed back to the LLM, per design spec
§3.1's token-economy note. `detail_level="detailed"` returns the full
payload unmodified.
"""

from __future__ import annotations

from typing import Any

# Fields stripped from each offer's `summary`/`supply`/`distribution`/`global`
# sub-objects (and from top-level `meta`) in summary mode — raw DB audit
# stamps and internal bookkeeping the LLM has no use for.
_AUDIT_FIELD_NAMES = {
    "source_value",
    "source_unit",
    "ingested_at",
    "raw",
    "internal_id",
    "row_hash",
    "created_at",
    "db_id",
}


def _strip_audit_fields(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_audit_fields(v) for k, v in obj.items() if k not in _AUDIT_FIELD_NAMES}
    if isinstance(obj, list):
        return [_strip_audit_fields(v) for v in obj]
    return obj


def format_price_response(payload: dict[str, Any], detail_level: str = "summary") -> dict[str, Any]:
    """Trim a /api/v1/prices JSON payload for the given detail level."""
    if detail_level == "detailed":
        return payload

    trimmed: dict[str, Any] = {}

    meta = payload.get("meta") or {}
    trimmed_meta = {
        "mode": meta.get("mode"),
        "date": meta.get("date"),
        "resolved": meta.get("resolved"),
        "last_updated_at": meta.get("last_updated_at") or meta.get("lastUpdatedAt"),
    }
    trimmed["meta"] = {k: v for k, v in trimmed_meta.items() if v is not None}

    offers = payload.get("offers") or []
    trimmed_offers = []
    for offer in offers:
        summary = offer.get("summary") or {}
        trimmed_offer = {
            "tariff_code": offer.get("tariff_code"),
            "region": offer.get("region"),
            "zones": offer.get("zones"),
            "summary": _strip_audit_fields(summary),
        }
        trimmed_offers.append({k: v for k, v in trimmed_offer.items() if v is not None})
    if trimmed_offers:
        trimmed["offers"] = trimmed_offers

    if payload.get("warnings"):
        trimmed["warnings"] = payload["warnings"]
    if payload.get("unmatched"):
        trimmed["unmatched"] = payload["unmatched"]

    return trimmed


def format_tariffs_markdown(tariffs: list[dict[str, Any]]) -> str:
    """Render a compact Markdown table for a list of tariff rows."""
    if not tariffs:
        return "_No tariffs found._"
    lines = ["| Code | Operator | Type | Zones | Region |", "|---|---|---|---|---|"]
    for t in tariffs:
        lines.append(
            "| {code} | {op} | {type} | {zones} | {region} |".format(
                code=t.get("tariff_code", "-"),
                op=t.get("operator_name", "-"),
                type=t.get("tariff_type", "-"),
                zones=t.get("zone_count", "-"),
                region=t.get("region", "-"),
            )
        )
    return "\n".join(lines)
