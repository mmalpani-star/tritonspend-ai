"""FastAPI HTTP boundary for the TritonSpend forecasting core."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from tritonspend.core.errors import TritonSpendError
from tritonspend.core.forecast import forecast

from .dependencies import today_provider
from .config import load_settings
from .auth_routes import router as auth_router
from .food_chat_routes import router as food_chat_router
from .food_routes import router as food_router
from .me_routes import router as me_router
from .venue_chat_routes import router as venue_chat_router
from .pilot_routes import router as pilot_router
from .mapping import to_core_input, to_response
from .schemas import ForecastRequest, ForecastResponse


settings = load_settings()
app = FastAPI(title="TritonSpend AI API", version="0.1.0")
logger = logging.getLogger("tritonspend")


async def _unhandled_errors_as_json(request: Request, call_next):
    """Turn an unexpected exception into a logged JSON 500 *inside* the CORS middleware.

    Starlette's default 500 is produced outside CORSMiddleware, so it lacks CORS headers and the
    browser reports it as a network failure ("Couldn't reach TritonSpend"). Registered before
    CORSMiddleware so CORS wraps it (Starlette runs the last-added middleware outermost).
    """
    try:
        return await call_next(request)
    except Exception:  # noqa: BLE001 - last-resort handler; the traceback is logged
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.middleware("http")(_unhandled_errors_as_json)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins or ("http://localhost:3000",)),
    allow_credentials=True,
    # PATCH edits and PUT votes are used by Food Chat.
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(auth_router)
app.include_router(pilot_router)
app.include_router(food_router)
app.include_router(food_chat_router)
app.include_router(me_router)
app.include_router(venue_chat_router)


@app.get("/api/v1/health")
def health() -> dict:
    """Liveness probe for the hosting platform. It deliberately does not touch the database, so
    frequent health checks never keep a scale-to-zero PostgreSQL compute (e.g. Neon) awake."""
    return {"status": "ok"}


@app.post("/api/v1/forecasts", response_model=ForecastResponse)
def create_forecast(
    request: ForecastRequest,
    today: date = Depends(today_provider),
) -> ForecastResponse:
    """Map a request to the core, run it once, and serialize its result."""
    try:
        core_input = to_core_input(request, today)
    except ValueError as exc:
        # Mapping rejects contract violations with ValueError; these are client errors.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        result = forecast(
            core_input.date_range,
            core_input.balances,
            core_input.habits,
            core_input.scenario,
        )
        return to_response(result)
    except TritonSpendError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
