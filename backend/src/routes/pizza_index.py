from fastapi import APIRouter, HTTPException

from src.models.schemas import (
    PizzaIndexSnapshotResponse,
    PizzaIndexTargetActivity,
    PizzaIndexTargetsResponse,
)
from src.services.seed_data import (
    get_latest_pizza_index,
    get_pizza_index_target_activity,
    list_pizza_index_targets,
    refresh_pizza_index,
)

router = APIRouter(prefix="/pizza-index", tags=["pizza-index"])


@router.get("/targets", response_model=PizzaIndexTargetsResponse)
def list_targets() -> PizzaIndexTargetsResponse:
    return list_pizza_index_targets()


@router.get("/targets/{target_id}/activity", response_model=PizzaIndexTargetActivity)
def get_target_activity(target_id: str) -> PizzaIndexTargetActivity:
    activity = get_pizza_index_target_activity(target_id)
    if activity is None:
        raise HTTPException(status_code=404, detail=f"Unknown pizza-index target: {target_id}")
    return activity


@router.get("/latest", response_model=PizzaIndexSnapshotResponse)
def get_latest_snapshot() -> PizzaIndexSnapshotResponse:
    return get_latest_pizza_index()


@router.post("/refresh", response_model=PizzaIndexSnapshotResponse)
def refresh_snapshot() -> PizzaIndexSnapshotResponse:
    return refresh_pizza_index()
