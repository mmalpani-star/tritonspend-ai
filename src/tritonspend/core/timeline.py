"""Inclusive date-range mechanics only."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterator

from .models import DateRange, ValidatedDateRange
from .validation import validate_date_range


def resolve_date_range(date_range: DateRange) -> ValidatedDateRange:
    """Validate a range and resolve its forecastable inclusive start date."""
    validate_date_range(date_range)
    projection_start = max(date_range.start, date_range.today)
    return ValidatedDateRange(
        start=date_range.start,
        end=date_range.end,
        today=date_range.today,
        projection_start=projection_start,
    )


def iter_dates(date_range: DateRange) -> Iterator[date]:
    """Yield projected dates from the resolved start through the end, inclusive."""
    resolved = resolve_date_range(date_range)
    current = resolved.projection_start
    while current <= resolved.end:
        yield current
        current += timedelta(days=1)
