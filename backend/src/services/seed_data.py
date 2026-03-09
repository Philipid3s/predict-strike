from src.models.schemas import (
    AlertEvaluationResponse,
    AlertHistoryResponse,
    MarketOpportunitiesResponse,
    PizzaIndexSnapshotResponse,
    PizzaIndexTargetActivity,
    PizzaIndexTargetsResponse,
)
from src.services.alert_pipeline import (
    evaluate_alerts as run_alert_evaluation,
    list_alert_history,
)
from src.services.market_pipeline import get_market_opportunities as load_market_opportunities
from src.services.pizza_index_pipeline import (
    build_latest_snapshot as load_latest_pizza_index_snapshot,
    get_target_activity as load_pizza_index_target_activity,
    list_targets as load_pizza_index_targets,
    refresh_snapshot as load_refreshed_pizza_index_snapshot,
)
from src.services.signal_pipeline import (
    get_or_create_latest_snapshot,
    refresh_latest_snapshot,
)


def get_latest_signals():
    return get_or_create_latest_snapshot()


def refresh_latest_signals():
    return refresh_latest_snapshot()


def get_market_opportunities() -> MarketOpportunitiesResponse:
    return load_market_opportunities()


def get_alerts() -> AlertHistoryResponse:
    return list_alert_history()


def evaluate_alerts() -> AlertEvaluationResponse:
    return run_alert_evaluation()


def list_pizza_index_targets() -> PizzaIndexTargetsResponse:
    return load_pizza_index_targets()


def get_pizza_index_target_activity(target_id: str) -> PizzaIndexTargetActivity | None:
    return load_pizza_index_target_activity(target_id)


def get_latest_pizza_index() -> PizzaIndexSnapshotResponse:
    return load_latest_pizza_index_snapshot()


def refresh_pizza_index() -> PizzaIndexSnapshotResponse:
    return load_refreshed_pizza_index_snapshot()
