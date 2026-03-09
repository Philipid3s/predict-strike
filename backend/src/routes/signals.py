from fastapi import APIRouter

from src.models.schemas import LatestSignalsResponse
from src.services.seed_data import get_latest_signals, refresh_latest_signals

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/latest", response_model=LatestSignalsResponse)
def get_latest_signal_snapshot() -> LatestSignalsResponse:
    return get_latest_signals()


@router.post("/refresh", response_model=LatestSignalsResponse)
def refresh_signal_snapshot() -> LatestSignalsResponse:
    return refresh_latest_signals()
