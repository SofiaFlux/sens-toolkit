"""Pydantic response models for the SENS API.

These mirror the shape of `com.energy.api.prices.dto.*` (PriceResponse,
Meta, Offer, ...) from the Kotlin backend closely enough to be useful, but
are deliberately defensive: every field is `Optional`, and every model sets
`extra="allow"` to tolerate backend schema drift without crashing the MCP
server. `formatter.py` is what actually trims fields for token economy — the
models here exist for structure and IDE/type-checker friendliness, not as a
strict contract.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class SensModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ResolvedParams(SensModel):
    dso: str | None = None
    retailer: str | None = None
    market: str | None = None
    tariff: str | None = None


class PaginationInfo(SensModel):
    page: int | None = None
    size: int | None = None
    has_more: bool | None = None


class Meta(SensModel):
    mode: str | None = None
    date: str | None = None
    pricing_basis: str | None = None
    resolved: ResolvedParams | None = None
    pagination: PaginationInfo | None = None
    last_updated_at: str | None = None


class PriceComponent(SensModel):
    name: str | None = None
    zone: str | None = None
    granularity: str | None = None
    value_pln_per_kwh: float | None = None
    value_pln_per_month: float | None = None
    source_value: float | None = None
    source_unit: str | None = None


class OfferSummary(SensModel):
    variable_total_pln_per_kwh: dict[str, float] | None = None
    fixed_total_pln_per_month: float | None = None
    fixed_total_note: str | None = None
    power_total_pln_per_kw_month: float | None = None
    variable_adder_pln_per_kwh: dict[str, float] | None = None
    energy_avg_pln_per_kwh: float | None = None
    total_avg_pln_per_kwh: float | None = None
    total_min_pln_per_kwh: float | None = None
    total_max_pln_per_kwh: float | None = None


class Offer(SensModel):
    tariff_code: str | None = None
    region: str | None = None
    variant: str | None = None
    zones: list[str] | None = None
    supply: dict[str, Any] | None = None
    distribution: dict[str, Any] | None = None
    global_: dict[str, Any] | None = None
    summary: OfferSummary | None = None

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class PriceResponse(SensModel):
    meta: Meta | None = None
    catalog: dict[str, Any] | None = None
    offers: list[Offer] = []
    unmatched: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []


class Tariff(SensModel):
    tariff_id: str | None = None
    operator_name: str | None = None
    operator_type: str | None = None
    tariff_type: str | None = None
    tariff_code: str | None = None
    zone_count: int | None = None
    voltage_level: str | None = None
    region: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    updated_at: str | None = None
    ingested_at: str | None = None


class TariffListResponse(SensModel):
    items: list[Tariff] = []
    meta: dict[str, Any] | None = None


class TariffComponent(SensModel):
    tariff_id: str | None = None
    name: str | None = None
    zone: str | None = None
    value_pln_per_kwh: float | None = None
    value_pln_per_month: float | None = None


class TariffComponentsResponse(SensModel):
    items: list[TariffComponent] = []
    meta: dict[str, Any] | None = None


class StructuredError(SensModel):
    """The actionable self-correction error envelope (design spec §4)."""

    status: str = "error"
    error_code: str
    message: str
    suggestions: dict[str, Any] | None = None
    remediation: str | None = None
    example_valid_call: str | None = None
