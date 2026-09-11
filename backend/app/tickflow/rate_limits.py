"""Small rate-limit helpers for batch market data fetches."""
from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from app.tickflow.capabilities import Cap, CapabilitySet

T = TypeVar("T")

SAFETY_RPM_FACTOR = 0.8


def apply_safety_rpm(rpm: int | None, *, factor: float = SAFETY_RPM_FACTOR) -> int | None:
    if rpm is None or rpm <= 0:
        return rpm
    return max(1, int(rpm * factor))


@dataclass(frozen=True)
class ResolvedLimit:
    batch: int | None
    rpm: int | None


def resolve_limit(
    capset: CapabilitySet,
    cap: Cap,
    *,
    default_batch: int | None = None,
    default_rpm: int | None = None,
    default_rpm_when_unset: bool = True,
    apply_safety: bool = True,
) -> ResolvedLimit:
    """Return a capability's batch/rpm with caller-provided fallbacks."""
    lim = capset.limits(cap)
    if lim is None:
        rpm = default_rpm
    else:
        rpm = lim.rpm if lim.rpm else (default_rpm if default_rpm_when_unset else None)
        default_batch = lim.batch if lim.batch else default_batch
    if apply_safety:
        rpm = apply_safety_rpm(rpm)
    return ResolvedLimit(batch=default_batch, rpm=rpm)


def chunked(items: Sequence[T] | Iterable[T], size: int | None) -> list[list[T]]:
    """Split *items* into batches of *size* (default 50)."""
    seq = list(items)
    n = int(size or 50)
    if n <= 0:
        n = 50
    return [seq[i : i + n] for i in range(0, len(seq), n)] or []


def sleep_between_batches(
    batch_index: int,
    rpm: int | None,
    *,
    default_interval: float = 0.0,
) -> None:
    """Sleep between batches based on requests-per-minute limit.

    batch_index is 0-based; first batch does not sleep. default_interval is
    accepted for 908 call-site compatibility and used when rpm is unset.
    """
    if batch_index <= 0:
        return
    if rpm and rpm > 0:
        delay = 60.0 / float(rpm)
    elif default_interval > 0:
        delay = default_interval
    else:
        return
    time.sleep(max(0.01, min(delay, 5.0)))
