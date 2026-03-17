from src.collectors.polymarket import PolymarketCollector
from src.config.settings import get_settings
from src.models.schemas import MarketOpportunitiesResponse, MarketOpportunity, SignalSource
from src.services.risk_engine import score_features
from src.services.signal_pipeline import get_or_create_latest_snapshot
from src.storage.signal_store import SignalStore

ALERT_EDGE_THRESHOLD = 0.05


def derive_trade_signal(edge: float) -> str:
    if edge > ALERT_EDGE_THRESHOLD:
        return "BUY"
    if edge < -ALERT_EDGE_THRESHOLD:
        return "SELL"
    return "HOLD"


def get_market_opportunities() -> MarketOpportunitiesResponse:
    settings = get_settings()
    snapshot = get_or_create_latest_snapshot()
    model_probability = score_features(snapshot.features.model_dump()).score

    collector = PolymarketCollector(
        source_url=settings.polymarket_gamma_url,
        pizzint_breaking_url=(
            settings.polymarket_pizzint_breaking_url
            or "https://www.pizzint.watch/api/markets/breaking?window=6h&final_limit=20&format=ticker"
        ),
    )
    observation = collector.fetch_observation()

    store = SignalStore(settings.database_url)
    store.save_source_observation(
        source_name="Polymarket",
        collected_at=observation.collected_at,
        status=observation.status,
        payload=observation.raw_payload,
    )

    opportunities: list[MarketOpportunity] = []
    for market in observation.markets:
        edge = round(model_probability - market.market_probability, 4)
        signal = derive_trade_signal(edge)

        opportunities.append(
            MarketOpportunity(
                market_id=market.market_id,
                question=market.question,
                market_probability=market.market_probability,
                model_probability=model_probability,
                edge=edge,
                signal=signal,
            )
        )

    opportunities.sort(key=lambda item: abs(item.edge), reverse=True)
    response = MarketOpportunitiesResponse(
        generated_at=observation.collected_at,
        source=SignalSource(
            name="Polymarket",
            status=observation.status,
            mode="live" if observation.status == "active" else "fallback",
            last_checked_at=observation.collected_at,
        ),
        upstream=observation.upstream,
        opportunities=opportunities[:10],
    )
    return store.save_market_opportunities(response)

