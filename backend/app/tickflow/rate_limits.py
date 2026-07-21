"""Small rate-limit helpers for batch market data fetches."""
from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from typing import TypeVar

T = TypeVar("T")


def chunked(items: Sequence[T] | Iterable[T], size: int | None) -> list[list[T]]:
    """Split *items* into batches of *size* (default 50)."""
    seq = list(items)
    n = int(size or 50)
    if n <= 0:
        n = 50
    return [seq[i : i + n] for i in range(0, len(seq), n)] or []


def sleep_between_batches(batch_index: int, rpm: int | None) -> None:
    """Sleep between batches based on requests-per-minute limit.

    batch_index is 0-based; first batch does not sleep.
    """
    if batch_index <= 0 or not rpm or rpm <= 0:
        return
    # minimum spacing between requests
    delay = 60.0 / float(rpm)
    # keep a small floor so we do not hammer local mock servers
    time.sleep(max(0.01, min(delay, 5.0)))
