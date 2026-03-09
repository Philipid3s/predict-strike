from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    service_name: str
    service_version: str
    api_base_path: str
    database_url: str
    cors_allowed_origins: tuple[str, ...]
    default_region_focus: str
    notam_source_url: str | None
    gdelt_source_url: str | None
    polymarket_gamma_url: str | None
    polymarket_pizzint_breaking_url: str | None
    pizza_index_enable_live_provider: bool
    pizza_index_dashboard_url: str | None
    serpapi_api_key: str | None
    serpapi_daily_limit: int
    pizza_index_provider_timeout_seconds: int
    pizza_index_node_binary: str

    @property
    def api_v1_prefix(self) -> str:
        return f"{self.api_base_path.rstrip('/')}/v1"


def get_settings() -> Settings:
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
        notam_source_url=os.getenv("NOTAM_SOURCE_URL"),
        gdelt_source_url=os.getenv("GDELT_SOURCE_URL"),
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
    )
