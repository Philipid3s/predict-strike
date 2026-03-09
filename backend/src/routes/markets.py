from fastapi import APIRouter

from src.models.schemas import MarketOpportunitiesResponse
from src.services.seed_data import get_market_opportunities

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("/opportunities", response_model=MarketOpportunitiesResponse)
def list_market_opportunities() -> MarketOpportunitiesResponse:
    return get_market_opportunities()
