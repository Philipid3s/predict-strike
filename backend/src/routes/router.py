from fastapi import APIRouter

from src.config.settings import get_settings
from src.routes.alerts import router as alerts_router
from src.routes.health import router as health_router
from src.routes.markets import router as markets_router
from src.routes.pizza_index import router as pizza_index_router
from src.routes.risk import router as risk_router
from src.routes.signals import router as signals_router

settings = get_settings()

api_router = APIRouter()
api_v1_router = APIRouter(prefix=settings.api_v1_prefix)

api_v1_router.include_router(signals_router)
api_v1_router.include_router(risk_router)
api_v1_router.include_router(markets_router)
api_v1_router.include_router(alerts_router)
api_v1_router.include_router(pizza_index_router)

api_router.include_router(health_router)
api_router.include_router(api_v1_router)
