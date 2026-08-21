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

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class SensModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ResolvedParams(SensModel):
    osd: Optional[str] = None
    sprzedawca: Optional[str] = None
    market: Optional[str] = None
    taryfa: Optional[str] = None


class PaginationInfo(SensModel):
    page: Optional[int] = None
    size: Optional[int] = None
    has_more: Optional[bool] = None


class Meta(SensModel):
    mode: Optional[str] = None
    date: Optional[str] = None
    pricing_basis: Optional[str] = None
    resolved: Optional[ResolvedParams] = None
    pagination: Optional[PaginationInfo] = None
    last_updated_at: Optional[str] = None


class PriceComponent(SensModel):
    name: Optional[str] = None
    zone: Optional[str] = None
    granularity: Optional[str] = None
    value_pln_per_kwh: Optional[float] = None
    value_pln_per_month: Optional[float] = None
    source_value: Optional[float] = None
    source_unit: Optional[str] = None


class OfferSummary(SensModel):
    variable_total_pln_per_kwh: Optional[dict[str, float]] = None
    fixed_total_pln_per_month: Optional[float] = None
    fixed_total_note: Optional[str] = None
    power_total_pln_per_kw_month: Optional[float] = None
    variable_adder_pln_per_kwh: Optional[dict[str, float]] = None
    energy_avg_pln_per_kwh: Optional[float] = None
    total_avg_pln_per_kwh: Optional[float] = None
    total_min_pln_per_kwh: Optional[float] = None
    total_max_pln_per_kwh: Optional[float] = None


class Offer(SensModel):
    tariff_code: Optional[str] = None
    region: Optional[str] = None
    variant: Optional[str] = None
    zones: Optional[list[str]] = None
    supply: Optional[dict[str, Any]] = None
    distribution: Optional[dict[str, Any]] = None
    global_: Optional[dict[str, Any]] = None
    summary: Optional[OfferSummary] = None

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class PriceResponse(SensModel):
    meta: Optional[Meta] = None
    catalog: Optional[dict[str, Any]] = None
    offers: list[Offer] = []
    unmatched: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []


class Tariff(SensModel):
    tariff_id: Optional[str] = None
    operator_name: Optional[str] = None
    operator_type: Optional[str] = None
    tariff_type: Optional[str] = None
    tariff_code: Optional[str] = None
    zone_count: Optional[int] = None
    voltage_level: Optional[str] = None
    region: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    updated_at: Optional[str] = None
    ingested_at: Optional[str] = None


class TariffListResponse(SensModel):
    items: list[Tariff] = []
    meta: Optional[dict[str, Any]] = None


class TariffComponent(SensModel):
    tariff_id: Optional[str] = None
    name: Optional[str] = None
    zone: Optional[str] = None
    value_pln_per_kwh: Optional[float] = None
    value_pln_per_month: Optional[float] = None


class TariffComponentsResponse(SensModel):
    items: list[TariffComponent] = []
    meta: Optional[dict[str, Any]] = None


class StructuredError(SensModel):
    """The actionable self-correction error envelope (design spec §4)."""

    status: str = "error"
    error_code: str
    message: str
    suggestions: Optional[dict[str, Any]] = None
    remediation: Optional[str] = None
    example_valid_call: Optional[str] = None
