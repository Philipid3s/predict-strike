from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from src.models.schemas import RiskScoreRequest, RiskScoreResponse

FEATURE_ORDER = (
    "flight_anomaly",
    "notam_spike",
    "satellite_buildup",
    "news_volume",
    "osint_activity",
    "pizza_index",
)

DEFAULT_WEIGHTS: dict[str, float] = {
    "flight_anomaly": 0.40,
    "notam_spike": 0.20,
    "satellite_buildup": 0.00,
    "news_volume": 0.2667,
    "osint_activity": 0.00,
    "pizza_index": 0.1333,
}

WATCH_THRESHOLD = 0.40
ALERT_THRESHOLD = 0.65


@dataclass(frozen=True)
class RiskContributionResult:
    feature: str
    value: float
    weight: float
    contribution: float


@dataclass(frozen=True)
class ScoreResult:
    score: float
    classification: str
    breakdown: list[RiskContributionResult]


def normalize_weights(overrides: Mapping[str, float] | None = None) -> dict[str, float]:
    weights = DEFAULT_WEIGHTS.copy()
    if overrides:
        weights.update(overrides)
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("Total weight must be greater than zero.")
    return {
        feature: weight / total_weight
        for feature, weight in weights.items()
        if feature in FEATURE_ORDER
    }


def classify_score(score: float) -> str:
    if score >= ALERT_THRESHOLD:
        return "alert"
    if score >= WATCH_THRESHOLD:
        return "watch"
    return "monitor"


def score_features(
    features: Mapping[str, float],
    overrides: Mapping[str, float] | None = None,
) -> ScoreResult:
    weights = normalize_weights(overrides)
    breakdown: list[RiskContributionResult] = []
    total_score = 0.0

    for feature in FEATURE_ORDER:
        value = float(features[feature])
        weight = weights[feature]
        contribution = round(value * weight, 4)
        total_score += contribution
        breakdown.append(
            RiskContributionResult(
                feature=feature,
                value=round(value, 4),
                weight=round(weight, 4),
                contribution=contribution,
            )
        )

    score = round(total_score, 4)
    return ScoreResult(
        score=score,
        classification=classify_score(score),
        breakdown=breakdown,
    )


def score_request(payload: "RiskScoreRequest") -> "RiskScoreResponse":
    from src.models.schemas import RiskContribution, RiskScoreResponse, RiskThresholds

    feature_values = payload.features.model_dump()
    weight_values = (
        payload.weights.model_dump(exclude_none=True)
        if payload.weights is not None
        else None
    )
    result = score_features(feature_values, weight_values)
    return RiskScoreResponse(
        score=result.score,
        classification=result.classification,
        breakdown=[
            RiskContribution(
                feature=item.feature,
                value=item.value,
                weight=item.weight,
                contribution=item.contribution,
            )
            for item in result.breakdown
        ],
        thresholds=RiskThresholds(
            watch=WATCH_THRESHOLD,
            alert=ALERT_THRESHOLD,
        ),
    )
