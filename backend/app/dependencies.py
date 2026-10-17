"""Injectable adapter dependencies."""

from datetime import date
from typing import Callable


TodayProvider = Callable[[], date]


def today_provider() -> date:
    """Return the server reference date for normal API requests."""
    return date.today()
