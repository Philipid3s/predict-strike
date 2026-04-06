from dataclasses import dataclass
import os
from pathlib import Path


_ENV_LOADED = False


def _load_backend_env_file() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        _ENV_LOADED = True
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value

    _ENV_LOADED = True


def _env_or_none(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _resolve_notam_env_value(environment: str, suffix: str, legacy_name: str) -> str | None:
    scoped_name = f"NOTAM_{environment.upper()}_{suffix}"
    scoped_value = _env_or_none(scoped_name)
    if scoped_value is not None:
        return scoped_value
    return _env_or_none(legacy_name)


@dataclass(frozen=True)
class Settings:
    service_name: str
    service_version: str
    api_base_path: str
    database_url: str
    cors_allowed_origins: tuple[str, ...]
    default_region_focus: str
    notam_environment: str
    notam_source_url: str | None
    notam_api_base_url: str | None
    notam_auth_url: str | None
    notam_client_id: str | None
    notam_client_secret: str | None
    notam_classification: str | None
    notam_accountability: str | None
    notam_location: str | None
    notam_response_format: str
    notam_detail_fetch_enabled: bool
    notam_max_items: int
    notam_timeout_seconds: int
    notam_ai_api_url: str | None
    notam_ai_api_key: str | None
    notam_ai_model: str | None
    notam_ai_timeout_seconds: int
    gdelt_source_url: str | None
    gdelt_timeout_seconds: int
    gdelt_ai_api_url: str | None
    gdelt_ai_api_key: str | None
    gdelt_ai_model: str | None
    gdelt_ai_timeout_seconds: int
    polymarket_gamma_url: str | None
    polymarket_pizzint_breaking_url: str | None
    pizza_index_enable_live_provider: bool
    pizza_index_dashboard_url: str | None
    serpapi_api_key: str | None
    serpapi_daily_limit: int
    pizza_index_provider_timeout_seconds: int
    pizza_index_node_binary: str
    opensky_ai_api_url: str | None
    opensky_ai_api_key: str | None
    opensky_ai_model: str | None
    opensky_ai_timeout_seconds: int

    @property
    def api_v1_prefix(self) -> str:
        return f"{self.api_base_path.rstrip('/')}/v1"


def get_settings() -> Settings:
    _load_backend_env_file()
    cors_allowed_origins = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        os.getenv(
            "CORS_ORIGIN",
            "http://localhost:5173,http://localhost,http://127.0.0.1:5173,http://127.0.0.1",
        ),
    )
    pizza_index_enable_live_provider = os.getenv(
        "PIZZA_INDEX_ENABLE_LIVE_PROVIDER", "true"
    ).strip().lower() in {"1", "true", "yes", "on"}
    notam_environment = os.getenv("NOTAM_ENV", "production").strip().lower()
    notam_detail_fetch_enabled = os.getenv(
        "NOTAM_DETAIL_FETCH_ENABLED",
        "false" if notam_environment == "production" else "true",
    ).strip().lower() in {"1", "true", "yes", "on"}
    return Settings(
        service_name=os.getenv("SERVICE_NAME", "predict-strike-backend"),
        service_version=os.getenv("SERVICE_VERSION", "0.1.0"),
        api_base_path=os.getenv("API_BASE_PATH", "/api"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./predict-strike.db"),
        cors_allowed_origins=tuple(
            origin.strip()
            for origin in cors_allowed_origins.split(",")
            if origin.strip()
        ),
        default_region_focus=os.getenv("DEFAULT_REGION_FOCUS", "global-watchlist"),
        notam_environment=notam_environment,
        notam_source_url=_resolve_notam_env_value(notam_environment, "SOURCE_URL", "NOTAM_SOURCE_URL"),
        notam_api_base_url=_resolve_notam_env_value(
            notam_environment, "API_BASE_URL", "NOTAM_API_BASE_URL"
        ),
        notam_auth_url=_resolve_notam_env_value(notam_environment, "AUTH_URL", "NOTAM_AUTH_URL"),
        notam_client_id=_resolve_notam_env_value(notam_environment, "CLIENT_ID", "NOTAM_CLIENT_ID"),
        notam_client_secret=_resolve_notam_env_value(
            notam_environment, "CLIENT_SECRET", "NOTAM_CLIENT_SECRET"
        ),
        notam_classification=_resolve_notam_env_value(
            notam_environment, "CLASSIFICATION", "NOTAM_CLASSIFICATION"
        ),
        notam_accountability=_resolve_notam_env_value(
            notam_environment, "ACCOUNTABILITY", "NOTAM_ACCOUNTABILITY"
        ),
        notam_location=_resolve_notam_env_value(notam_environment, "LOCATION", "NOTAM_LOCATION"),
        notam_response_format=os.getenv("NOTAM_RESPONSE_FORMAT", "GEOJSON").strip().upper(),
        notam_detail_fetch_enabled=notam_detail_fetch_enabled,
        notam_max_items=max(int(os.getenv("NOTAM_MAX_ITEMS", "20")), 1),
        notam_timeout_seconds=max(int(os.getenv("NOTAM_TIMEOUT_SECONDS", "10")), 1),
        notam_ai_api_url=os.getenv(
            "NOTAM_AI_API_URL",
            "https://api.openai.com/v1/chat/completions",
        ),
        notam_ai_api_key=os.getenv("NOTAM_AI_API_KEY"),
        notam_ai_model=os.getenv("NOTAM_AI_MODEL"),
        notam_ai_timeout_seconds=max(
            int(os.getenv("NOTAM_AI_TIMEOUT_SECONDS", "15")),
            1,
        ),
        gdelt_source_url=os.getenv("GDELT_SOURCE_URL"),
        gdelt_timeout_seconds=max(
            int(os.getenv("GDELT_TIMEOUT_SECONDS", "30")),
            1,
        ),
        gdelt_ai_api_url=os.getenv(
            "GDELT_AI_API_URL",
            "https://api.openai.com/v1/chat/completions",
        ),
        gdelt_ai_api_key=os.getenv("GDELT_AI_API_KEY"),
        gdelt_ai_model=os.getenv("GDELT_AI_MODEL"),
        gdelt_ai_timeout_seconds=max(
            int(os.getenv("GDELT_AI_TIMEOUT_SECONDS", "15")),
            1,
        ),
        polymarket_gamma_url=os.getenv("POLYMARKET_GAMMA_URL"),
        polymarket_pizzint_breaking_url=os.getenv("POLYMARKET_PIZZINT_BREAKING_URL"),
        pizza_index_enable_live_provider=pizza_index_enable_live_provider,
        pizza_index_dashboard_url=os.getenv("PIZZA_INDEX_DASHBOARD_URL"),
        serpapi_api_key=os.getenv("SERPAPI_API_KEY"),
        serpapi_daily_limit=max(int(os.getenv("SERPAPI_DAILY_LIMIT", "4")), 0),
        pizza_index_provider_timeout_seconds=max(
            int(os.getenv("PIZZA_INDEX_PROVIDER_TIMEOUT_SECONDS", "8")),
            1,
        ),
        pizza_index_node_binary=os.getenv("PIZZA_INDEX_NODE_BINARY", "node"),
        opensky_ai_api_url=os.getenv(
            "OPENSKY_AI_API_URL",
            "https://api.openai.com/v1/chat/completions",
        ),
        opensky_ai_api_key=os.getenv("OPENSKY_AI_API_KEY"),
        opensky_ai_model=os.getenv("OPENSKY_AI_MODEL"),
        opensky_ai_timeout_seconds=max(
            int(os.getenv("OPENSKY_AI_TIMEOUT_SECONDS", "15")),
            1,
        ),
    )
