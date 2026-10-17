"""Domain errors raised by the deterministic budget core."""


class TritonSpendError(ValueError):
    """Base class for invalid domain values."""


class InvalidMoneyError(TritonSpendError):
    """A balance or price is not a non-negative integer number of cents."""


class InvalidDateRangeError(TritonSpendError):
    """A date range or reference date is invalid."""
