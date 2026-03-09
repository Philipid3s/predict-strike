from datetime import UTC, datetime

from src.config.settings import get_settings
from src.models.schemas import (
    AlertEvaluationResponse,
    AlertHistoryResponse,
    AlertRecord,
)
from src.services.market_pipeline import get_market_opportunities
from src.storage.signal_store import SignalStore


def _utc_now() -> datetime:
    return datetime.now(UTC)


def list_alert_history() -> AlertHistoryResponse:
    store = SignalStore(get_settings().database_url)
    return AlertHistoryResponse(generated_at=_utc_now(), alerts=store.list_alerts())


def evaluate_alerts() -> AlertEvaluationResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    opportunity_response = get_market_opportunities()

    created_at = _utc_now()
    pending_alerts = [
        AlertRecord(
            id="0",
            created_at=created_at,
            market_id=opportunity.market_id,
            question=opportunity.question,
            market_probability=opportunity.market_probability,
            model_probability=opportunity.model_probability,
            edge=opportunity.edge,
            signal=opportunity.signal,
            status="open",
        )
        for opportunity in opportunity_response.opportunities
        if opportunity.signal != "HOLD"
    ]

    persisted_alerts = store.save_alerts(pending_alerts) if pending_alerts else []
    return AlertEvaluationResponse(
        evaluated_at=created_at,
        created_count=len(persisted_alerts),
        alerts=persisted_alerts,
    )
