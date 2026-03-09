from fastapi import APIRouter

from src.models.schemas import AlertEvaluationResponse, AlertHistoryResponse
from src.services.alert_pipeline import evaluate_alerts, list_alert_history

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertHistoryResponse)
def get_alert_history() -> AlertHistoryResponse:
    return list_alert_history()


@router.post("/evaluate", response_model=AlertEvaluationResponse)
def evaluate_current_alerts() -> AlertEvaluationResponse:
    return evaluate_alerts()
