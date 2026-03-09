from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from src.collectors.pizzint import fetch_dashboard_payload
from src.config.settings import Settings, get_settings
from src.models.schemas import (
    PizzaIndexDataQuality,
    PizzaIndexProvider,
    PizzaIndexProviderMode,
    PizzaIndexQualitySummary,
    PizzaIndexSnapshotResponse,
    PizzaIndexTarget,
    PizzaIndexTargetActivity,
    PizzaIndexTargetContribution,
    PizzaIndexTargetsResponse,
)
from src.storage.signal_store import SignalStore

CACHE_TTL = timedelta(minutes=10)


@dataclass(frozen=True)
class PizzaIndexTargetDefinition:
    target_id: str
    display_name: str
    category: str
    priority_weight: float
    location_cluster: str
    pizzint_place_id: str | None
    google_maps_url: str
    serpapi_query: str
    active: bool = True


TARGET_REGISTRY: tuple[PizzaIndexTargetDefinition, ...] = (
    PizzaIndexTargetDefinition(
        target_id="dominos_pentagon_city",
        display_name="Domino's Pizza - Pentagon City",
        category="pizza",
        priority_weight=1.0,
        location_cluster="pentagon-city",
        pizzint_place_id="ChIJI6ACK7q2t4kRFcPtFhUuYhU",
        google_maps_url="https://www.google.com/maps/place/Domino's+Pizza/@38.8627308,-77.0879692,17z/data=!3m1!4b1!4m6!3m5!1s0x89b7b6ba2b02a023:0x15622e1516edc315!8m2!3d38.8627267!4d-77.0853943!16s%2Fg%2F1wbryp46?entry=ttu&g_ep=EgoyMDI1MDYxNi4wIKXMDSoASAFQAw%3D%3D",
        serpapi_query="Domino's Pizza Pentagon City",
    ),
    PizzaIndexTargetDefinition(
        target_id="papa_johns_pentagon_city",
        display_name="Papa Johns Pizza - Pentagon City",
        category="pizza",
        priority_weight=0.95,
        location_cluster="pentagon-city",
        pizzint_place_id="ChIJo03BaX-3t4kRbyhPM0rTuqM",
        google_maps_url="https://www.google.com/maps/place/Papa+Johns+Pizza/@38.8292633,-77.1901741,11.83z/data=!4m6!3m5!1s0x89b7b77f69c14da3:0xa3bad34a334f286f!8m2!3d38.8606821!4d-77.0922272!16s%2Fg%2F11t104lmtl?entry=ttu&g_ep=EgoyMDI1MDYxNy4wIKXMDSoASAFQAw%3D%3D",
        serpapi_query="Papa Johns Pizza Pentagon City",
    ),
    PizzaIndexTargetDefinition(
        target_id="we_the_pizza_pentagon_row",
        display_name="We The Pizza - Pentagon Row",
        category="pizza",
        priority_weight=0.9,
        location_cluster="pentagon-row",
        pizzint_place_id="ChIJS1rpOC-3t4kRsLyM6aftM8k",
        google_maps_url="https://www.google.com/maps/place/We,+The+Pizza/@38.8663614,-77.0588449,15.76z/data=!3m1!5s0x89b7b72f331803b7:0x7edf0a3adffa41c8!4m6!3m5!1s0x89b7b72f38e95a4b:0xc933eda7e98cbcb0!8m2!3d38.8551791!4d-77.049733!16s%2Fg%2F1q62g66vf?entry=ttu&g_ep=EgoyMDI1MDYxNi4wIKXMDSoASAFQAw%3D%3D",
        serpapi_query="We The Pizza Pentagon Row",
    ),
    PizzaIndexTargetDefinition(
        target_id="extreme_pizza_pentagon_row",
        display_name="Extreme Pizza - Pentagon Row",
        category="pizza",
        priority_weight=0.85,
        location_cluster="pentagon-row",
        pizzint_place_id="ChIJcYireCe3t4kR4d9trEbGYjc",
        google_maps_url="https://www.google.com/maps/place/Extreme+Pizza/@38.8602396,-77.0585603,17z/data=!3m1!4b1!4m6!3m5!1s0x89b7b72778ab8871:0x3762c646ac6ddfe1!8m2!3d38.8602396!4d-77.0559854!16s%2Fg%2F12llsn19l?entry=ttu&g_ep=EgoyMDI1MDYxNi4wIKXMDSoASAFQAw%3D%3D",
        serpapi_query="Extreme Pizza Pentagon Row",
    ),
    PizzaIndexTargetDefinition(
        target_id="wiseguy_pizza_rosslyn",
        display_name="Wiseguy Pizza - Rosslyn",
        category="pizza",
        priority_weight=0.8,
        location_cluster="rosslyn",
        pizzint_place_id=None,
        google_maps_url="https://www.google.com/maps/place/Wiseguy+Pizza+Rosslyn",
        serpapi_query="Wiseguy Pizza Rosslyn",
    ),
)

STUB_ACTIVITY_FIXTURES: dict[str, dict[str, Any]] = {
    "dominos_pentagon_city": {
        "is_open": True,
        "current_busyness_percent": 63,
        "usual_busyness_percent": 46,
        "busyness_delta_percent": 17,
        "current_busyness_label": "busier_than_usual",
        "rating": 4.1,
        "reviews_count": 812,
        "address": "Pentagon City, Arlington, VA",
    },
    "papa_johns_pentagon_city": {
        "is_open": True,
        "current_busyness_percent": 59,
        "usual_busyness_percent": 42,
        "busyness_delta_percent": 17,
        "current_busyness_label": "busier_than_usual",
        "rating": 4.0,
        "reviews_count": 603,
        "address": "Pentagon City, Arlington, VA",
    },
    "we_the_pizza_pentagon_row": {
        "is_open": True,
        "current_busyness_percent": 56,
        "usual_busyness_percent": 44,
        "busyness_delta_percent": 12,
        "current_busyness_label": "slightly_busier_than_usual",
        "rating": 4.2,
        "reviews_count": 944,
        "address": "Pentagon Row, Arlington, VA",
    },
    "extreme_pizza_pentagon_row": {
        "is_open": True,
        "current_busyness_percent": 48,
        "usual_busyness_percent": 39,
        "busyness_delta_percent": 9,
        "current_busyness_label": "slightly_busier_than_usual",
        "rating": 4.0,
        "reviews_count": 321,
        "address": "Pentagon Row, Arlington, VA",
    },
    "wiseguy_pizza_rosslyn": {
        "is_open": True,
        "current_busyness_percent": 52,
        "usual_busyness_percent": 37,
        "busyness_delta_percent": 15,
        "current_busyness_label": "busier_than_usual",
        "rating": 4.3,
        "reviews_count": 488,
        "address": "Rosslyn, Arlington, VA",
    },
}


def list_targets() -> PizzaIndexTargetsResponse:
    return PizzaIndexTargetsResponse(
        generated_at=_utcnow(),
        targets=[_to_target_model(target) for target in TARGET_REGISTRY if target.active],
    )


def get_target_activity(target_id: str) -> PizzaIndexTargetActivity | None:
    target = _find_target(target_id)
    if target is None:
        return None

    settings = get_settings()
    store = _get_store(settings)
    cached = store.get_pizza_index_target_activity(target_id)
    if (
        cached is not None
        and _is_recent(cached.collected_at)
        and _is_supported_provider(cached.provider)
    ):
        return cached

    return _collect_and_cache_target_activity(target, settings=settings, store=store)


def build_latest_snapshot() -> PizzaIndexSnapshotResponse:
    settings = get_settings()
    store = _get_store(settings)
    cached = store.get_pizza_index_snapshot()
    if (
        cached is not None
        and _is_recent(cached.generated_at)
        and all(_is_supported_provider(target.provider) for target in cached.targets)
    ):
        return cached

    dashboard_items: dict[str, dict[str, Any]] | None
    dashboard_failure_reason: str | None = None
    try:
        dashboard_items = (
            _load_pizzint_item_lookup(settings) if settings.pizza_index_enable_live_provider else None
        )
    except Exception as exc:
        dashboard_items = {}
        dashboard_failure_reason = f"pizzint_failed:{exc}"
    target_activities = [
        _collect_and_cache_target_activity(
            target,
            settings=settings,
            store=store,
            dashboard_items=dashboard_items,
            dashboard_failure_reason=dashboard_failure_reason,
        )
        for target in TARGET_REGISTRY
        if target.active
    ]
    snapshot = _build_snapshot_from_activities(
        [activity for activity in target_activities if activity is not None]
    )
    return store.save_pizza_index_snapshot(snapshot)


def refresh_snapshot() -> PizzaIndexSnapshotResponse:
    settings = get_settings()
    store = _get_store(settings)
    dashboard_items: dict[str, dict[str, Any]] | None
    dashboard_failure_reason: str | None = None
    try:
        dashboard_items = (
            _load_pizzint_item_lookup(settings) if settings.pizza_index_enable_live_provider else None
        )
    except Exception as exc:
        dashboard_items = {}
        dashboard_failure_reason = f"pizzint_failed:{exc}"
    refreshed = [
        _collect_and_cache_target_activity(
            target,
            settings=settings,
            store=store,
            dashboard_items=dashboard_items,
            dashboard_failure_reason=dashboard_failure_reason,
        )
        for target in TARGET_REGISTRY
        if target.active
    ]
    snapshot = _build_snapshot_from_activities(refreshed)
    return store.save_pizza_index_snapshot(snapshot)


def fetch_pizzint_dashboard_payload(settings: Settings) -> dict[str, Any]:
    return fetch_dashboard_payload(
        source_url=settings.pizza_index_dashboard_url,
        timeout_seconds=settings.pizza_index_provider_timeout_seconds,
    )


def fetch_serpapi_place_payload(
    target: PizzaIndexTargetDefinition,
    api_key: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    query = urlencode(
        {
            "engine": "google_maps",
            "q": target.serpapi_query,
            "api_key": api_key,
        }
    )
    url = f"https://serpapi.com/search.json?{query}"
    with urlopen(url, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))

    place = _extract_serpapi_place(payload)
    current = _pick_int(
        place,
        "current_busyness_percent",
        "live_popularity",
        "popular_times_live_percent",
        "current_popularity",
    )
    usual = _pick_int(
        place,
        "usual_busyness_percent",
        "usual_popularity_percent",
        "usual_popularity",
    )
    delta = _pick_int(place, "busyness_delta_percent")
    if delta is None and current is not None and usual is not None:
        delta = current - usual

    current_label = _pick_str(place, "current_busyness_label", "live_popularity_description")
    capture_status = "serpapi_google_maps_ok"
    if current is None and usual is None and delta is None:
        capture_status = "serpapi_google_maps_partial"

    return {
        "display_name": _pick_str(place, "title", "name") or target.display_name,
        "address": _pick_str(place, "address"),
        "rating": _pick_float(place, "rating"),
        "reviews_count": _pick_int(place, "reviews", "reviews_count"),
        "is_open": _pick_bool(place, "open_state", "open_now"),
        "current_busyness_percent": current,
        "usual_busyness_percent": usual,
        "busyness_delta_percent": delta,
        "current_busyness_label": current_label,
        "capture_status": capture_status,
    }


def _load_pizzint_item_lookup(settings: Settings) -> dict[str, dict[str, Any]]:
    payload = fetch_pizzint_dashboard_payload(settings)
    items = payload.get("data")
    if not isinstance(items, list):
        raise RuntimeError("pizzint dashboard payload did not include a data array")

    lookup: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        place_id = _coerce_optional_str(item.get("place_id"))
        if place_id is not None:
            lookup[place_id] = item
    return lookup


def _select_pizzint_payload_for_target(
    target: PizzaIndexTargetDefinition,
    item_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if target.pizzint_place_id is None:
        return {
            "google_maps_url": target.google_maps_url,
            "capture_status": "pizzint_target_not_mapped",
        }

    item = item_lookup.get(target.pizzint_place_id)
    if item is None:
        return {
            "google_maps_url": target.google_maps_url,
            "capture_status": "pizzint_target_missing_from_dashboard",
            "pizzint_place_id": target.pizzint_place_id,
        }
    return dict(item)


def _normalize_pizzint_item(item: dict[str, Any]) -> dict[str, Any]:
    collected_at = _utcnow()
    google_maps_url = _coerce_optional_str(item.get("address"))
    display_name = _coerce_optional_str(item.get("name"))
    current = _coerce_optional_int(item.get("current_popularity"), minimum=0, maximum=100)
    ratio = _coerce_optional_float(item.get("percentage_of_usual"), minimum=0.0)
    usual = None
    if current is not None and ratio is not None and ratio > 0:
        usual = _coerce_optional_int(round(current * 100.0 / ratio), minimum=0, maximum=100)
    if usual is None:
        usual = _baseline_popularity_for_now(item.get("baseline_popular_times"), collected_at=collected_at)

    is_closed_now = _coerce_optional_bool(item.get("is_closed_now"))
    if current is None and is_closed_now is False and isinstance(item.get("sparkline_24h"), list):
        current = _latest_non_null_current(item["sparkline_24h"])
    if current is None and is_closed_now is True:
        current = 0
    if usual is None and is_closed_now is True:
        usual = 0

    delta = None
    if current is not None and usual is not None:
        delta = current - usual

    capture_status = "pizzint_dashboard_ok"
    if is_closed_now is True and current == 0:
        capture_status = "pizzint_dashboard_ok_closed"
    elif current is None and usual is None:
        capture_status = "pizzint_dashboard_partial"

    return {
        "display_name": display_name,
        "google_maps_url": google_maps_url,
        "current_busyness_percent": current,
        "usual_busyness_percent": usual,
        "busyness_delta_percent": delta,
        "current_busyness_label": _label_busyness(current=current, usual=usual, is_open=not is_closed_now if is_closed_now is not None else None),
        "is_open": None if is_closed_now is None else not is_closed_now,
        "capture_status": capture_status,
        "pizzint_place_id": _coerce_optional_str(item.get("place_id")),
        "data_source": _coerce_optional_str(item.get("data_source")),
    }


def _get_store(settings: Settings) -> SignalStore:
    return SignalStore(settings.database_url)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _is_recent(timestamp: datetime, *, now: datetime | None = None) -> bool:
    reference = now or _utcnow()
    return reference - timestamp <= CACHE_TTL


def _find_target(target_id: str) -> PizzaIndexTargetDefinition | None:
    for target in TARGET_REGISTRY:
        if target.target_id == target_id:
            return target
    return None


def _to_target_model(target: PizzaIndexTargetDefinition) -> PizzaIndexTarget:
    return PizzaIndexTarget(
        target_id=target.target_id,
        display_name=target.display_name,
        category=target.category,
        priority_weight=target.priority_weight,
        location_cluster=target.location_cluster,
        google_maps_url=target.google_maps_url,
        active=target.active,
    )


def _collect_and_cache_target_activity(
    target: PizzaIndexTargetDefinition,
    *,
    settings: Settings,
    store: SignalStore,
    dashboard_items: dict[str, dict[str, Any]] | None = None,
    dashboard_failure_reason: str | None = None,
) -> PizzaIndexTargetActivity:
    activity = _collect_target_activity(
        target,
        settings=settings,
        store=store,
        dashboard_items=dashboard_items,
        dashboard_failure_reason=dashboard_failure_reason,
    )
    return store.save_pizza_index_target_activity(activity)


def _collect_target_activity(
    target: PizzaIndexTargetDefinition,
    *,
    settings: Settings,
    store: SignalStore,
    dashboard_items: dict[str, dict[str, Any]] | None = None,
    dashboard_failure_reason: str | None = None,
) -> PizzaIndexTargetActivity:
    collected_at = _utcnow()
    if not settings.pizza_index_enable_live_provider:
        return _build_stub_activity(
            target,
            collected_at=collected_at,
            data_quality="partial",
            capture_status="live_provider_disabled_using_stub_fixture",
            unavailable=False,
        )

    try:
        item_lookup = dashboard_items
        if item_lookup == {} and dashboard_failure_reason is not None:
            raise RuntimeError(dashboard_failure_reason)
        if item_lookup is None:
            item_lookup = _load_pizzint_item_lookup(settings)
        pizzint_raw_payload = _select_pizzint_payload_for_target(target, item_lookup)
        normalized_pizzint_payload = (
            _normalize_pizzint_item(pizzint_raw_payload)
            if "place_id" in pizzint_raw_payload
            else pizzint_raw_payload
        )
        store.save_pizza_index_provider_payload(
            target_id=target.target_id,
            provider="pizzint",
            provider_mode="primary",
            collected_at=collected_at,
            payload={**pizzint_raw_payload, **normalized_pizzint_payload},
        )
        if _has_meaningful_pizzint_data(normalized_pizzint_payload):
            return _build_activity(
                target,
                provider="pizzint",
                provider_mode="primary",
                collected_at=collected_at,
                payload=normalized_pizzint_payload,
            )
        primary_failure_reason = str(
            normalized_pizzint_payload.get("capture_status", "pizzint_missing_busyness_data")
        )
    except Exception as exc:
        primary_failure_reason = str(exc)

    fallback_activity = _attempt_serpapi_fallback(
        target,
        settings=settings,
        store=store,
        collected_at=collected_at,
        failure_reason=primary_failure_reason,
    )
    if fallback_activity is not None:
        return fallback_activity

    return _build_stub_activity(
        target,
        collected_at=collected_at,
        data_quality="unavailable",
        capture_status=f"{primary_failure_reason};no_fallback_available",
        unavailable=True,
    )


def _attempt_serpapi_fallback(
    target: PizzaIndexTargetDefinition,
    *,
    settings: Settings,
    store: SignalStore,
    collected_at: datetime,
    failure_reason: str,
) -> PizzaIndexTargetActivity | None:
    if not settings.serpapi_api_key:
        return None

    allowed, _ = store.try_consume_provider_daily_quota(
        provider_name="serpapi",
        usage_date=date.today(),
        daily_limit=settings.serpapi_daily_limit,
    )
    if not allowed:
        return _build_stub_activity(
            target,
            collected_at=collected_at,
            data_quality="unavailable",
            capture_status=f"{failure_reason};serpapi_daily_budget_exhausted",
            unavailable=True,
        )

    try:
        serpapi_payload = fetch_serpapi_place_payload(
            target,
            api_key=settings.serpapi_api_key,
            timeout_seconds=settings.pizza_index_provider_timeout_seconds,
        )
        store.save_pizza_index_provider_payload(
            target_id=target.target_id,
            provider="serpapi",
            provider_mode="fallback",
            collected_at=collected_at,
            payload=serpapi_payload,
        )
    except Exception as exc:
        return _build_stub_activity(
            target,
            collected_at=collected_at,
            data_quality="unavailable",
            capture_status=f"{failure_reason};serpapi_failed:{exc}",
            unavailable=True,
        )

    return _build_activity(
        target,
        provider="serpapi",
        provider_mode="fallback",
        collected_at=collected_at,
        payload=serpapi_payload,
    )


def _build_activity(
    target: PizzaIndexTargetDefinition,
    *,
    provider: PizzaIndexProvider,
    provider_mode: PizzaIndexProviderMode,
    collected_at: datetime,
    payload: dict[str, Any],
) -> PizzaIndexTargetActivity:
    current = _coerce_optional_int(payload.get("current_busyness_percent"), minimum=0, maximum=100)
    usual = _coerce_optional_int(payload.get("usual_busyness_percent"), minimum=0, maximum=100)
    delta = _coerce_optional_int(payload.get("busyness_delta_percent"), minimum=-100, maximum=100)
    if delta is None and current is not None and usual is not None:
        delta = current - usual

    capture_status = str(payload.get("capture_status", f"{provider}_capture"))
    quality = _infer_quality(
        current=current,
        usual=usual,
        delta=delta,
        has_secondary_metadata=any(
            payload.get(field) is not None
            for field in ("address", "rating", "reviews_count", "is_open")
        ),
    )
    return PizzaIndexTargetActivity(
        target_id=target.target_id,
        display_name=str(payload.get("display_name") or target.display_name),
        provider=provider,
        provider_mode=provider_mode,
        collected_at=collected_at,
        data_quality=quality,
        capture_status=capture_status,
        is_open=_coerce_optional_bool(payload.get("is_open")),
        current_busyness_percent=current,
        usual_busyness_percent=usual,
        busyness_delta_percent=delta,
        current_busyness_label=_coerce_optional_str(payload.get("current_busyness_label")),
        rating=_coerce_optional_float(payload.get("rating"), minimum=0.0, maximum=5.0),
        reviews_count=_coerce_optional_int(payload.get("reviews_count"), minimum=0),
        address=_coerce_optional_str(payload.get("address")),
        google_maps_url=_coerce_optional_str(payload.get("google_maps_url")) or target.google_maps_url,
    )


def _build_stub_activity(
    target: PizzaIndexTargetDefinition,
    *,
    collected_at: datetime,
    data_quality: PizzaIndexDataQuality,
    capture_status: str,
    unavailable: bool,
) -> PizzaIndexTargetActivity:
    fixture = STUB_ACTIVITY_FIXTURES.get(target.target_id, {})
    return PizzaIndexTargetActivity(
        target_id=target.target_id,
        display_name=target.display_name,
        provider="stub",
        provider_mode="stub",
        collected_at=collected_at,
        data_quality=data_quality,
        capture_status=capture_status,
        is_open=None if unavailable else fixture.get("is_open"),
        current_busyness_percent=None if unavailable else fixture.get("current_busyness_percent"),
        usual_busyness_percent=None if unavailable else fixture.get("usual_busyness_percent"),
        busyness_delta_percent=None if unavailable else fixture.get("busyness_delta_percent"),
        current_busyness_label=None if unavailable else fixture.get("current_busyness_label"),
        rating=None if unavailable else fixture.get("rating"),
        reviews_count=None if unavailable else fixture.get("reviews_count"),
        address=None if unavailable else fixture.get("address"),
        google_maps_url=target.google_maps_url,
    )


def _has_meaningful_busyness(payload: dict[str, Any]) -> bool:
    return any(
        payload.get(field) is not None
        for field in (
            "current_busyness_percent",
            "usual_busyness_percent",
            "busyness_delta_percent",
            "current_busyness_label",
        )
    )


def _has_meaningful_pizzint_data(payload: dict[str, Any]) -> bool:
    return _has_meaningful_busyness(payload) or any(
        payload.get(field) is not None
        for field in (
            "address",
            "rating",
            "reviews_count",
            "is_open",
        )
    )


def _infer_quality(
    *,
    current: int | None,
    usual: int | None,
    delta: int | None,
    has_secondary_metadata: bool,
) -> PizzaIndexDataQuality:
    if current is not None and usual is not None and delta is not None:
        return "full"
    if current is not None or usual is not None or delta is not None or has_secondary_metadata:
        return "partial"
    return "unavailable"


def _build_snapshot_from_activities(
    activities: list[PizzaIndexTargetActivity],
) -> PizzaIndexSnapshotResponse:
    contributions: list[PizzaIndexTargetContribution] = []
    total_weight = sum(target.priority_weight for target in TARGET_REGISTRY if target.active)
    weighted_score_total = 0.0
    weighted_quality_total = 0.0
    full_count = 0
    partial_count = 0
    unavailable_count = 0

    weight_lookup = {target.target_id: target.priority_weight for target in TARGET_REGISTRY}
    display_lookup = {target.target_id: target.display_name for target in TARGET_REGISTRY}

    for activity in activities:
        weight = weight_lookup.get(activity.target_id, 1.0)
        quality_weight = _quality_weight(activity.data_quality)
        open_factor = _open_factor(activity.is_open)
        delta = max(activity.busyness_delta_percent or 0, 0)
        normalized_delta = _clamp(delta / 50.0)
        target_score = _clamp(normalized_delta * weight * quality_weight * open_factor)

        weighted_score_total += normalized_delta * weight * quality_weight * open_factor
        weighted_quality_total += weight * quality_weight

        if activity.data_quality == "full":
            full_count += 1
        elif activity.data_quality == "partial":
            partial_count += 1
        else:
            unavailable_count += 1

        contributions.append(
            PizzaIndexTargetContribution(
                target_id=activity.target_id,
                display_name=display_lookup.get(activity.target_id, activity.display_name),
                target_score=target_score,
                weight=weight,
                data_quality=activity.data_quality,
                provider=activity.provider,
            )
        )

    pizza_index = 0.0 if total_weight <= 0 else _clamp(weighted_score_total / total_weight)
    confidence = 0.0 if total_weight <= 0 else _clamp(weighted_quality_total / total_weight)

    return PizzaIndexSnapshotResponse(
        generated_at=_utcnow(),
        pizza_index=pizza_index,
        pizza_index_confidence=confidence,
        quality_summary=PizzaIndexQualitySummary(
            full_count=full_count,
            partial_count=partial_count,
            unavailable_count=unavailable_count,
        ),
        targets=contributions,
    )


def _quality_weight(data_quality: PizzaIndexDataQuality) -> float:
    return {
        "full": 1.0,
        "partial": 0.4,
        "unavailable": 0.0,
    }[data_quality]


def _open_factor(is_open: bool | None) -> float:
    if is_open is True:
        return 1.0
    if is_open is False:
        return 0.0
    return 0.5


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(value, maximum))


def _is_supported_provider(provider: str) -> bool:
    return provider in {"pizzint", "serpapi", "stub"}


def _baseline_popularity_for_now(
    baseline_payload: Any,
    *,
    collected_at: datetime,
) -> int | None:
    if not isinstance(baseline_payload, dict):
        return None

    eastern_now = collected_at.astimezone(ZoneInfo("America/New_York"))
    day_index = eastern_now.isoweekday() % 7
    day_rows = baseline_payload.get(str(day_index))
    if not isinstance(day_rows, list):
        return None

    for row in day_rows:
        if not isinstance(row, dict):
            continue
        if _coerce_optional_int(row.get("hour")) != eastern_now.hour:
            continue
        return _coerce_optional_int(row.get("popularity"), minimum=0, maximum=100)
    return None


def _latest_non_null_current(sparkline_rows: list[Any]) -> int | None:
    for row in reversed(sparkline_rows):
        if not isinstance(row, dict):
            continue
        current = _coerce_optional_int(row.get("current_popularity"), minimum=0, maximum=100)
        if current is not None:
            return current
    return None


def _label_busyness(
    *,
    current: int | None,
    usual: int | None,
    is_open: bool | None,
) -> str | None:
    if is_open is False:
        return "closed"
    if current is None or usual is None:
        return None
    if usual <= 0:
        return "no_baseline" if current > 0 else "no_activity"

    ratio = current / usual
    if ratio >= 1.25:
        return "busier_than_usual"
    if ratio >= 1.05:
        return "slightly_busier_than_usual"
    if ratio <= 0.75:
        return "quieter_than_usual"
    return "as_usual"


def _extract_serpapi_place(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("place_results"), dict):
        return payload["place_results"]
    local_results = payload.get("local_results")
    if isinstance(local_results, list) and local_results:
        first = local_results[0]
        if isinstance(first, dict):
            return first
    return payload


def _pick_int(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = _coerce_optional_int(payload.get(key))
        if value is not None:
            return value
    return None


def _pick_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _coerce_optional_float(payload.get(key))
        if value is not None:
            return value
    return None


def _pick_str(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _coerce_optional_str(payload.get(key))
        if value is not None:
            return value
    return None


def _pick_bool(payload: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = _coerce_optional_bool(payload.get(key))
        if value is not None:
            return value
    return None


def _coerce_optional_int(
    value: Any,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if minimum is not None and parsed < minimum:
        return None
    if maximum is not None and parsed > maximum:
        return None
    return parsed


def _coerce_optional_float(
    value: Any,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if minimum is not None and parsed < minimum:
        return None
    if maximum is not None and parsed > maximum:
        return None
    return parsed


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _coerce_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"open", "open_now", "true", "1", "yes"}:
        return True
    if normalized in {"closed", "false", "0", "no"}:
        return False
    return None
