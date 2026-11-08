from datetime import date

import pytest

from tritonspend.core.errors import InvalidDateRangeError
from tritonspend.core.models import DateRange
from tritonspend.core.timeline import iter_dates, resolve_date_range


TODAY = date(2026, 10, 16)


def test_iter_dates_includes_both_requested_boundaries():
    dates = DateRange(date(2026, 10, 16), date(2026, 10, 18), TODAY)

    assert list(iter_dates(dates)) == [
        date(2026, 10, 16),
        date(2026, 10, 17),
        date(2026, 10, 18),
    ]


def test_start_before_today_projects_from_today():
    dates = DateRange(date(2026, 10, 1), date(2026, 10, 17), TODAY)

    resolved = resolve_date_range(dates)

    assert resolved.projection_start == TODAY
    assert list(iter_dates(dates)) == [TODAY, date(2026, 10, 17)]


def test_end_before_today_is_rejected_explicitly():
    dates = DateRange(date(2026, 10, 1), date(2026, 10, 15), TODAY)

    with pytest.raises(InvalidDateRangeError):
        list(iter_dates(dates))


def test_one_day_range_when_start_today_and_end_today():
    dates = DateRange(TODAY, TODAY, TODAY)

    assert list(iter_dates(dates)) == [TODAY]


def test_range_before_today_ending_today_includes_today_only():
    dates = DateRange(date(2026, 10, 1), TODAY, TODAY)

    assert list(iter_dates(dates)) == [TODAY]
