"""Injectable adapter dependencies."""

from datetime import date, datetime
from typing import Callable
from zoneinfo import ZoneInfo


TodayProvider = Callable[[], date]


def today_provider() -> date:
    """Return the server reference date for normal API requests."""
    return date.today()


def pilot_today_provider() -> date:
    """Return the participant calendar date, matching the pilot routes' timezone."""
    return datetime.now(ZoneInfo("America/Los_Angeles")).date()
