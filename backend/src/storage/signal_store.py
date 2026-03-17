from datetime import date, datetime
import json
from pathlib import Path
import sqlite3

from src.models.schemas import (
    AlertRecord,
    FeatureSet,
    LatestSignalsResponse,
    MarketOpportunitiesResponse,
    PizzaIndexSnapshotResponse,
    PizzaIndexTargetActivity,
    SignalSource,
)


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def database_path_from_url(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Only sqlite:/// URLs are supported.")

    raw_path = database_url[len(prefix) :]
    path = Path(raw_path)
    if not path.is_absolute():
        path = _backend_root() / path
    return path.resolve()


class SignalStore:
    def __init__(self, database_url: str) -> None:
        self._database_path = database_path_from_url(database_url)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._database_path))
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS source_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS signal_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generated_at TEXT NOT NULL,
                    region_focus TEXT NOT NULL,
                    features_json TEXT NOT NULL,
                    sources_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    market_probability REAL NOT NULL,
                    model_probability REAL NOT NULL,
                    edge REAL NOT NULL,
                    signal TEXT NOT NULL,
                    status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS market_opportunity_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generated_at TEXT NOT NULL,
                    source_json TEXT NOT NULL,
                    upstream TEXT NOT NULL,
                    opportunities_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alert_evaluation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evaluated_at TEXT NOT NULL,
                    created_count INTEGER NOT NULL,
                    alerts_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS provider_daily_usage (
                    provider_name TEXT NOT NULL,
                    usage_date TEXT NOT NULL,
                    request_count INTEGER NOT NULL,
                    PRIMARY KEY (provider_name, usage_date)
                );

                CREATE TABLE IF NOT EXISTS pizza_index_target_activity_cache (
                    target_id TEXT PRIMARY KEY,
                    collected_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pizza_index_provider_payloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_mode TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pizza_index_snapshot_cache (
                    cache_key TEXT PRIMARY KEY,
                    generated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def save_source_observation(
        self,
        *,
        source_name: str,
        collected_at: datetime,
        status: str,
        payload: dict,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO source_observations (
                    source_name,
                    collected_at,
                    status,
                    payload_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    source_name,
                    collected_at.isoformat(),
                    status,
                    json.dumps(payload),
                ),
            )

    def save_signal_snapshot(self, snapshot: LatestSignalsResponse) -> LatestSignalsResponse:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO signal_snapshots (
                    generated_at,
                    region_focus,
                    features_json,
                    sources_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    snapshot.generated_at.isoformat(),
                    snapshot.region_focus,
                    json.dumps(snapshot.features.model_dump(mode="json")),
                    json.dumps([source.model_dump(mode="json") for source in snapshot.sources]),
                ),
            )
        return snapshot

    def get_latest_signal_snapshot(self) -> LatestSignalsResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT generated_at, region_focus, features_json, sources_json
                FROM signal_snapshots
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        if row is None:
            return None

        return LatestSignalsResponse(
            generated_at=datetime.fromisoformat(row["generated_at"]),
            region_focus=row["region_focus"],
            features=FeatureSet(**json.loads(row["features_json"])),
            sources=[
                SignalSource(**self._coerce_source_payload(source))
                for source in json.loads(row["sources_json"])
            ],
        )

    def get_latest_source_observation(self, source_name: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT collected_at, status, payload_json
                FROM source_observations
                WHERE source_name = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (source_name,),
            ).fetchone()

        if row is None:
            return None

        return {
            "collected_at": row["collected_at"],
            "status": row["status"],
            "payload": json.loads(row["payload_json"]),
        }

    @staticmethod
    def _coerce_source_payload(source: dict) -> dict:
        payload = dict(source)
        if "mode" not in payload:
            status = payload.get("status")
            if status == "active":
                payload["mode"] = "live"
            elif status == "degraded":
                payload["mode"] = "fallback"
            else:
                payload["mode"] = "static_baseline"
        return payload

    def save_alerts(self, alerts: list[AlertRecord]) -> list[AlertRecord]:
        persisted: list[AlertRecord] = []
        with self._connect() as connection:
            for alert in alerts:
                cursor = connection.execute(
                    """
                    INSERT INTO alerts (
                        created_at,
                        market_id,
                        question,
                        market_probability,
                        model_probability,
                        edge,
                        signal,
                        status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        alert.created_at.isoformat(),
                        alert.market_id,
                        alert.question,
                        alert.market_probability,
                        alert.model_probability,
                        alert.edge,
                        alert.signal,
                        alert.status,
                    ),
                )
                persisted.append(alert.model_copy(update={"id": str(cursor.lastrowid)}))
        return persisted

    def save_market_opportunities(
        self, snapshot: MarketOpportunitiesResponse
    ) -> MarketOpportunitiesResponse:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO market_opportunity_snapshots (
                    generated_at,
                    source_json,
                    upstream,
                    opportunities_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    snapshot.generated_at.isoformat(),
                    json.dumps(snapshot.source.model_dump(mode="json")),
                    snapshot.upstream,
                    json.dumps(
                        [
                            opportunity.model_dump(mode="json")
                            for opportunity in snapshot.opportunities
                        ]
                    ),
                ),
            )
        return snapshot

    def save_alert_evaluation_run(
        self,
        *,
        evaluated_at: datetime,
        created_count: int,
        alerts: list[AlertRecord],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO alert_evaluation_runs (
                    evaluated_at,
                    created_count,
                    alerts_json
                ) VALUES (?, ?, ?)
                """,
                (
                    evaluated_at.isoformat(),
                    created_count,
                    json.dumps([alert.model_dump(mode="json") for alert in alerts]),
                ),
            )

    def list_alerts(self, limit: int = 100) -> list[AlertRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    created_at,
                    market_id,
                    question,
                    market_probability,
                    model_probability,
                    edge,
                    signal,
                    status
                FROM alerts
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            AlertRecord(
                id=str(row["id"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                market_id=row["market_id"],
                question=row["question"],
                market_probability=float(row["market_probability"]),
                model_probability=float(row["model_probability"]),
                edge=float(row["edge"]),
                signal=row["signal"],
                status=row["status"],
            )
            for row in rows
        ]

    def get_provider_daily_usage(self, provider_name: str, usage_date: date) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT request_count
                FROM provider_daily_usage
                WHERE provider_name = ? AND usage_date = ?
                """,
                (provider_name, usage_date.isoformat()),
            ).fetchone()

        if row is None:
            return 0
        return int(row["request_count"])

    def try_consume_provider_daily_quota(
        self,
        *,
        provider_name: str,
        usage_date: date,
        daily_limit: int,
    ) -> tuple[bool, int]:
        usage_date_value = usage_date.isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT request_count
                FROM provider_daily_usage
                WHERE provider_name = ? AND usage_date = ?
                """,
                (provider_name, usage_date_value),
            ).fetchone()
            current_count = 0 if row is None else int(row["request_count"])

            if current_count >= daily_limit:
                connection.commit()
                return False, current_count

            next_count = current_count + 1
            connection.execute(
                """
                INSERT INTO provider_daily_usage (
                    provider_name,
                    usage_date,
                    request_count
                ) VALUES (?, ?, ?)
                ON CONFLICT(provider_name, usage_date)
                DO UPDATE SET request_count = excluded.request_count
                """,
                (provider_name, usage_date_value, next_count),
            )
            connection.commit()
            return True, next_count

    def save_pizza_index_target_activity(
        self, activity: PizzaIndexTargetActivity
    ) -> PizzaIndexTargetActivity:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pizza_index_target_activity_cache (
                    target_id,
                    collected_at,
                    payload_json
                ) VALUES (?, ?, ?)
                ON CONFLICT(target_id)
                DO UPDATE SET
                    collected_at = excluded.collected_at,
                    payload_json = excluded.payload_json
                """,
                (
                    activity.target_id,
                    activity.collected_at.isoformat(),
                    json.dumps(activity.model_dump(mode="json")),
                ),
            )
        return activity

    def save_pizza_index_provider_payload(
        self,
        *,
        target_id: str,
        provider: str,
        provider_mode: str,
        collected_at: datetime,
        payload: dict,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pizza_index_provider_payloads (
                    target_id,
                    provider,
                    provider_mode,
                    collected_at,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    target_id,
                    provider,
                    provider_mode,
                    collected_at.isoformat(),
                    json.dumps(payload),
                ),
            )

    def get_pizza_index_target_activity(
        self, target_id: str
    ) -> PizzaIndexTargetActivity | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM pizza_index_target_activity_cache
                WHERE target_id = ?
                """,
                (target_id,),
            ).fetchone()

        if row is None:
            return None

        return PizzaIndexTargetActivity(**json.loads(row["payload_json"]))

    def get_latest_pizza_index_provider_payload(
        self,
        *,
        target_id: str,
        provider: str | None = None,
    ) -> dict | None:
        query = """
                SELECT payload_json
                FROM pizza_index_provider_payloads
                WHERE target_id = ?
                """
        params: tuple = (target_id,)
        if provider is not None:
            query += " AND provider = ?"
            params = (target_id, provider)
        query += " ORDER BY id DESC LIMIT 1"

        with self._connect() as connection:
            row = connection.execute(query, params).fetchone()

        if row is None:
            return None
        return json.loads(row["payload_json"])

    def save_pizza_index_snapshot(
        self, snapshot: PizzaIndexSnapshotResponse
    ) -> PizzaIndexSnapshotResponse:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pizza_index_snapshot_cache (
                    cache_key,
                    generated_at,
                    payload_json
                ) VALUES (?, ?, ?)
                ON CONFLICT(cache_key)
                DO UPDATE SET
                    generated_at = excluded.generated_at,
                    payload_json = excluded.payload_json
                """,
                (
                    "latest",
                    snapshot.generated_at.isoformat(),
                    json.dumps(snapshot.model_dump(mode="json")),
                ),
            )
        return snapshot

    def get_pizza_index_snapshot(self) -> PizzaIndexSnapshotResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM pizza_index_snapshot_cache
                WHERE cache_key = 'latest'
                """
            ).fetchone()

        if row is None:
            return None

        return PizzaIndexSnapshotResponse(**json.loads(row["payload_json"]))


