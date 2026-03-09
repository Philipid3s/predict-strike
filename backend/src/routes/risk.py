from fastapi import APIRouter

from src.models.schemas import RiskScoreRequest, RiskScoreResponse
from src.services.risk_engine import score_request

router = APIRouter(prefix="/risk", tags=["risk"])


@router.post("/score", response_model=RiskScoreResponse)
def score_risk(payload: RiskScoreRequest) -> RiskScoreResponse:
    return score_request(payload)
