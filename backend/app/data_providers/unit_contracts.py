"""Unit admission checks at provider publication boundaries."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Literal

from app.data_providers.base import ProviderDatasetManifest

VolumeUnit = Literal["share", "lot", "contract", "unknown"]
AmountUnit = Literal["CNY", "TEN_THOUSAND_CNY", "USD", "HKD", "unknown"]
RatioScale = Literal["fraction", "percentage_point", "unknown"]
TimestampUnit = Literal["date", "s", "ms", "iso8601"]


class UnitContractError(ValueError):
    """Raised when a provider cannot safely publish into the canonical contract."""


CN_CANONICAL_UNITS: Mapping[str, str] = {
    "volume": "lot",
    "amount": "CNY",
    "ratio": "percentage_point",
    "daily_timestamp": "date",
    "realtime_timestamp": "iso8601",
    "realtime_timezone": "UTC",
    "market_timezone": "Asia/Shanghai",
    "shares": "share",
}


def _volume_unit(value: str) -> VolumeUnit:
    unit = value.strip().lower()
    if unit in {"share", "lot", "contract", "unknown"}:
        return unit  # type: ignore[return-value]
    raise UnitContractError(f"unsupported volume unit: {value}")


def _amount_unit(value: str) -> AmountUnit:
    aliases = {"cny": "CNY", "ten_thousand_cny": "TEN_THOUSAND_CNY"}
    raw = value.strip()
    unit = aliases.get(raw, raw if raw == "unknown" else raw.upper())
    if unit in {"CNY", "TEN_THOUSAND_CNY", "USD", "HKD", "unknown"}:
        return unit  # type: ignore[return-value]
    raise UnitContractError(f"unsupported amount unit: {value}")


def _ratio_scale(value: str) -> RatioScale:
    scale = value.strip().lower()
    if scale in {"fraction", "percentage_point", "unknown"}:
        return scale  # type: ignore[return-value]
    raise UnitContractError(f"unsupported ratio scale: {value}")


def canonicalize_volume(
    value: float | None, source_unit: VolumeUnit, *, market: str
) -> float | None:
    """Convert a declared CN source volume to canonical lots."""
    if value is None:
        return None
    if market.upper() != "CN":
        raise UnitContractError("CN volume canonicalization is not valid for non-CN markets")
    unit = _volume_unit(source_unit)
    if unit == "share":
        return value / 100
    if unit == "lot":
        return value
    raise UnitContractError(f"volume unit {unit!r} cannot publish as CN lots")


def canonicalize_amount(
    value: float | None, source_unit: AmountUnit, *, market: str
) -> float | None:
    """Convert a declared CN source amount to canonical CNY."""
    if value is None:
        return None
    if market.upper() != "CN":
        raise UnitContractError("CN amount canonicalization is not valid for non-CN markets")
    unit = _amount_unit(source_unit)
    if unit == "CNY":
        return value
    if unit == "TEN_THOUSAND_CNY":
        return value * 10_000
    raise UnitContractError(f"amount unit {unit!r} cannot publish as CN CNY")


def canonicalize_ratio(
    value: float | None,
    source_scale: RatioScale,
    *,
    target_scale: RatioScale,
) -> float | None:
    """Convert declared ratio scales without guessing their semantics."""
    if value is None:
        return None
    source = _ratio_scale(source_scale)
    target = _ratio_scale(target_scale)
    if "unknown" in {source, target}:
        raise UnitContractError("unknown ratio scale cannot be published")
    if source == target:
        return value
    if source == "fraction" and target == "percentage_point":
        return value * 100
    if source == "percentage_point" and target == "fraction":
        return value / 100
    raise UnitContractError(f"unsupported ratio conversion: {source} -> {target}")


def ensure_publishable_units(
    manifest: ProviderDatasetManifest,
    *,
    required_fields: Collection[str],
    market: str,
) -> None:
    """Reject undeclared units before a provider is contacted or data is written."""
    source_units = manifest.source_units
    canonical_units = manifest.canonical_units
    ordered_fields = [field for field in ("volume", "amount") if field in required_fields]
    ordered_fields.extend(sorted(set(required_fields) - {"volume", "amount"}))
    for field in ordered_fields:
        source_unit = source_units.get(field, "unknown")
        normalized_field = field.lower()
        if "volume" in normalized_field:
            if _volume_unit(source_unit) == "unknown":
                raise UnitContractError(f"unknown {field} unit is not publishable")
        elif "amount" in normalized_field and _amount_unit(source_unit) == "unknown":
            raise UnitContractError(f"unknown {field} unit is not publishable")

    if market.upper() != "CN" and {
        canonical_units.get("volume"),
        canonical_units.get("amount"),
    } & {"lot", "CNY"}:
        raise UnitContractError("non-CN publication cannot use the CN lot/CNY canonical contract")
