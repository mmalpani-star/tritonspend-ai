"""Domain errors raised by the deterministic budget core."""


class TritonSpendError(ValueError):
    """Base class for invalid domain values."""


class InvalidMoneyError(TritonSpendError):
    """A balance or price is not a non-negative integer number of cents."""


class InvalidExpenseError(TritonSpendError):
    """An expense amount or payment eligibility declaration is invalid."""


class InvalidHabitError(TritonSpendError):
    """A structured spending habit is invalid."""


class InvalidForecastError(TritonSpendError):
    """Forecast configuration or input is invalid."""


class InvalidDateRangeError(TritonSpendError):
    """A date range or reference date is invalid."""
