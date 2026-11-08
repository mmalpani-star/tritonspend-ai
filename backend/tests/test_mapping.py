from datetime import date
from fractions import Fraction

import pytest
from pydantic import ValidationError

from backend.app.mapping import parse_frequency, to_core_input, to_response
from backend.app.schemas import ForecastRequest
from tritonspend.core.forecast import forecast
from tritonspend.core.models import PaymentAccount


TODAY = date(2026, 10, 16)


def request(**overrides):
    value = {
        "start_date": "2026-10-16",
        "end_date": "2026-10-18",
        "dining_dollars_cents": 1_000,
        "triton_cash_cents": 500,
        "habits": [
            {
                "name": "breakfast",
                "frequency": "1/2",
                "price_cents": 375,
                "eligible_accounts": ["dining_dollars"],
            }
        ],
    }
    value.update(overrides)
    return ForecastRequest.model_validate(value)


def test_mapping_uses_injected_today_and_existing_core_types():
    mapped = to_core_input(request(), TODAY)

    assert mapped.date_range.today == TODAY
    assert mapped.balances.dining_dollars.cents == 1_000
    assert mapped.habits[0].frequency == Fraction(1, 2)
    assert mapped.habits[0].price.cents == 375
    assert mapped.habits[0].eligible_accounts == (PaymentAccount.DINING_DOLLARS,)


@pytest.mark.parametrize("value", ["0.5", "1/0", "-1/2", "1/2/3", True, 0.5])
def test_frequency_contract_rejects_non_strict_values(value):
    if isinstance(value, str):
        with pytest.raises(ValueError):
            parse_frequency(value)
    else:
        with pytest.raises((TypeError, ValueError, ValidationError)):
            ForecastRequest.model_validate({
                **request().model_dump(),
                "habits": [{**request().model_dump()["habits"][0], "frequency": value}],
            })


def test_frequency_contract_accepts_fraction_strings_only():
    assert parse_frequency("3/7") == Fraction(3, 7)
    assert parse_frequency("2") == Fraction(2)


@pytest.mark.parametrize(
    "accounts",
    [[], ["dining_dollars", "dining_dollars"], ["unknown"]],
)
def test_eligibility_must_be_non_empty_known_and_duplicate_free(accounts):
    with pytest.raises(ValidationError):
        request(
            habits=[
                {
                    "name": "meal",
                    "frequency": "1",
                    "price_cents": 100,
                    "eligible_accounts": accounts,
                }
            ]
        )


def test_default_expected_scenario_maps_and_response_preserves_core_values():
    mapped = to_core_input(request(), TODAY)
    response = to_response(forecast(
        mapped.date_range,
        mapped.balances,
        mapped.habits,
        mapped.scenario,
    ))

    assert response.scenario == "expected"
    assert response.multiplier == "1"
    assert response.days[0].date == TODAY
    assert response.limits.daily_wallet_runway_caps.dining_dollars_cents == 333


def test_request_forbids_today_and_unknown_fields():
    with pytest.raises(ValidationError):
        request(today="2026-10-16")
    with pytest.raises(ValidationError):
        request(unexpected=True)
