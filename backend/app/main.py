"""FastAPI HTTP boundary for the TritonSpend forecasting core."""

from __future__ import annotations

from datetime import date

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from tritonspend.core.errors import TritonSpendError
from tritonspend.core.forecast import forecast

from .dependencies import today_provider
from .config import load_settings
from .auth_routes import router as auth_router
from .pilot_routes import router as pilot_router
from .mapping import to_core_input, to_response
from .schemas import ForecastRequest, ForecastResponse


settings = load_settings()
app = FastAPI(title="TritonSpend AI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins or ("http://localhost:3000",)),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(auth_router)
app.include_router(pilot_router)


@app.post("/api/v1/forecasts", response_model=ForecastResponse)
def create_forecast(
    request: ForecastRequest,
    today: date = Depends(today_provider),
) -> ForecastResponse:
    """Map a request to the core, run it once, and serialize its result."""
    try:
        core_input = to_core_input(request, today)
        result = forecast(
            core_input.date_range,
            core_input.balances,
            core_input.habits,
            core_input.scenario,
        )
        return to_response(result)
    except TritonSpendError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
