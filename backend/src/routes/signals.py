from fastapi import APIRouter, HTTPException, status

from src.models.schemas import (
    GdeltDetailResponse,
    GdeltSignalRefreshResponse,
    LatestSignalsResponse,
    NotamDetailResponse,
    NotamSignalRefreshResponse,
    OpenSkyAnomaliesResponse,
    OpenSkySignalRefreshResponse,
    SignalSourceRefreshRequest,
    SignalSourceRefreshResponse,
)
from src.services.seed_data import (
    get_latest_signals,
    get_latest_gdelt_detail,
    get_latest_notam_detail,
    get_latest_opensky_anomalies,
    refresh_gdelt_signal,
    refresh_notam_signal,
    refresh_opensky_signal,
    refresh_latest_signals,
    refresh_signal_source,
    refresh_source_detail,
)

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/latest", response_model=LatestSignalsResponse)
def get_latest_signal_snapshot() -> LatestSignalsResponse:
    return get_latest_signals()


@router.post("/refresh", response_model=LatestSignalsResponse)
def refresh_signal_snapshot() -> LatestSignalsResponse:
    return refresh_latest_signals()


@router.post("/refresh-source", response_model=SignalSourceRefreshResponse)
def refresh_individual_signal_source(
    request: SignalSourceRefreshRequest,
) -> SignalSourceRefreshResponse:
    try:
        return refresh_signal_source(request.source_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/sources/opensky-network/refresh-source",
    response_model=SignalSourceRefreshResponse,
)
def refresh_opensky_source_detail() -> SignalSourceRefreshResponse:
    return refresh_source_detail("OpenSky Network")


@router.post(
    "/sources/notam-feed/refresh-source",
    response_model=SignalSourceRefreshResponse,
)
def refresh_notam_source_detail() -> SignalSourceRefreshResponse:
    return refresh_source_detail("NOTAM Feed")


@router.post(
    "/sources/gdelt/refresh-source",
    response_model=SignalSourceRefreshResponse,
)
def refresh_gdelt_source_detail() -> SignalSourceRefreshResponse:
    return refresh_source_detail("GDELT")


@router.get("/sources/opensky-network/anomalies", response_model=OpenSkyAnomaliesResponse)
def get_opensky_anomalies() -> OpenSkyAnomaliesResponse:
    return get_latest_opensky_anomalies()


@router.post(
    "/sources/opensky-network/refresh-signal",
    response_model=OpenSkySignalRefreshResponse,
)
def refresh_opensky_signal_feature() -> OpenSkySignalRefreshResponse:
    return refresh_opensky_signal()


@router.get("/sources/gdelt/detail", response_model=GdeltDetailResponse)
def get_gdelt_detail() -> GdeltDetailResponse:
    return get_latest_gdelt_detail()


@router.get("/sources/notam-feed/detail", response_model=NotamDetailResponse)
def get_notam_detail() -> NotamDetailResponse:
    return get_latest_notam_detail()


@router.post(
    "/sources/notam-feed/refresh-signal",
    response_model=NotamSignalRefreshResponse,
)
def refresh_notam_signal_feature() -> NotamSignalRefreshResponse:
    return refresh_notam_signal()


@router.post(
    "/sources/gdelt/refresh-signal",
    response_model=GdeltSignalRefreshResponse,
)
def refresh_gdelt_signal_feature() -> GdeltSignalRefreshResponse:
    return refresh_gdelt_signal()
