# Predict Strike Initial Project Spec

This document is the working kickoff specification for **Predict Strike**. It
captures the initial product direction, MVP boundaries, and implementation
shape for the first planning phase.

## 1. Objective

Build an automated system that:

1. Collects OSINT signals related to military, political, and media activity.
2. Transforms those signals into a **conflict risk score**.
3. Compares that score with probabilities on prediction markets such as
   Polymarket.
4. Generates analyst-facing alerts when markets appear mispriced.

## 2. High-Level Architecture

```text
Data Sources
   ->
Collectors / Ingestion
   ->
Signal Extraction & Normalization
   ->
Risk Scoring Model
   ->
Prediction Market Scanner
   ->
Alert Engine
   ->
Dashboard / Logs
```

## 3. Modules

### A. Data Collection

#### 1) Military Flight Tracking

**OpenSky Network API** collects aircraft flight data such as position, speed,
and altitude.

Example endpoint:

```text
GET https://opensky-network.org/api/states/all
```

Use cases:

- detect tanker aircraft spikes
- identify AWACS and reconnaissance flights
- track heavy transport activity

Example signal:

- unusual spike of military-type aircraft near conflict regions

#### 2) Naval Tracking

Sources:

- MarineTraffic (limited free tier)
- AIS open vessel feeds

Signals:

- concentration of naval vessels
- carrier groups leaving port
- support ships moving toward operational zones

#### 3) NOTAM Monitoring

NOTAM = Notice to Air Missions.

Signals:

- temporary restricted airspace
- missile tests
- military exercises

Implementation:

- scrape public NOTAM feeds
- track sudden appearance of large restricted areas

#### 4) Satellite Monitoring

Sources:

- Sentinel Hub
- NASA Worldview

Signals:

- troop buildup
- large vehicle accumulation
- construction of temporary bases

#### 5) Social Media OSINT

Sources:

- Telegram OSINT channels
- X / Twitter accounts
- Reddit communities

Signals:

- videos of military convoys
- soldier deployment posts
- eyewitness footage

#### 6) News Monitoring

Sources:

- GDELT DOC 2.0
- Google News scraping

Signals:

- spikes in conflict-related keywords
- rising geopolitical tension narratives

#### 7) Pentagon Pizza Index Monitoring

The **Pentagon Pizza Index** is an informal OSINT indicator suggesting that
spikes in pizza deliveries near U.S. defense and intelligence facilities may
precede major military operations or geopolitical crises.

The hypothesis is that **large operational planning meetings lead to increased
late-night food orders** from nearby restaurants.

This type of signal falls into the category of **behavioral intelligence
indicators**.

Possible data sources:

- **Google Maps**
  - restaurant "popular times"
  - real-time busyness indicators
- **Google Trends**
  - searches such as `pizza delivery Washington DC`
  - searches such as `pizza near Pentagon`
  - searches such as `late night food DC`
- **Uber Eats / DoorDash**
  - restaurant availability
  - unusual delivery demand signals
- **Social media monitoring**
  - posts mentioning large pizza orders
  - restaurant posts showing unusual demand

Geographic focus:

- **The Pentagon**
- **White House Situation Room**
- **CIA Headquarters (Langley)**

Signals:

- abnormal restaurant busyness after midnight
- sudden surge in delivery activity
- unusual spikes in food delivery searches
- social media posts mentioning large pizza orders

Example signal:

```python
pizza_activity_index = normalized_restaurant_activity_score
```

This signal should remain low-confidence unless corroborated by stronger
operational or narrative evidence.

### B. Signal Processing

Raw data must be normalized into structured features such as:

- aircraft activity anomaly score
- naval movement anomaly
- restricted airspace activity
- satellite detected buildup
- news narrative intensity
- OSINT alert density
- pizza activity index

Example feature structure:

```json
{
  "flight_anomaly": 0.7,
  "naval_anomaly": 0.4,
  "notam_spike": 0.3,
  "satellite_buildup": 0.5,
  "news_volume": 0.6,
  "osint_activity": 0.4,
  "pizza_index": 0.2
}
```

Normalization guidelines:

- keep feature names stable and versioned
- store raw observations separately from derived features
- preserve timestamps, source identifiers, and collection status

### C. Risk Scoring Model

A lightweight weighted scoring system can convert signals into a conflict
probability estimate.

Example formula:

```python
risk_score = (
    w1 * aircraft_anomaly
    + w2 * notam_spike
    + w3 * satellite_buildup
    + w4 * news_spike
    + w5 * osint_activity
)
```

Weights can later be optimized using historical events, but the MVP should stay
transparent and explainable.

### D. Prediction Market Scanner

The system queries the Polymarket API to retrieve markets related to
geopolitical events.

Data extracted:

- market question
- current probability
- trading volume
- last update time

Example comparison logic:

```python
if risk_score > threshold and market_price < predicted_probability:
    signal = "BUY"
elif risk_score < lower_threshold and market_price > predicted_probability:
    signal = "SELL"
```

For the MVP, these comparisons should create alerts for analysts rather than
placing trades automatically.

### E. Alert / Execution Engine

Possible outputs:

- Telegram notifications
- Slack alerts
- email reports
- optional automated trading integration

**MVP default:** alerts only.

### F. Dashboard (Optional)

Simple web dashboard showing:

- current risk score
- historical signal timeline
- prediction market comparisons
- alerts and trades

Possible implementation:

- FastAPI backend
- React frontend

## 4. APIs and Data Sources

| Source | Data Type | Access |
| --- | --- | --- |
| OpenSky Network | Aircraft flight tracking | REST |
| MarineTraffic / AIS feeds | Ship tracking | API |
| NOTAM feeds | Airspace restrictions | scrape/API |
| Sentinel Hub | Satellite imagery | API |
| NASA Worldview | Satellite monitoring | API |
| GDELT DOC 2.0 | Global news monitoring | API |
| Telegram / Twitter | OSINT social signals | scraping |
| Polymarket | Prediction market data | API |

## 5. Suggested Tech Stack

- **Primary language:** Python
- **Backend:** FastAPI
- **Database:** SQLite
- **Caching:** Redis
- **Task scheduling:** Celery or cron
- **Dashboard:** React frontend

Initial implementation guidance:

- use FastAPI for API and internal service endpoints
- start with SQLite for local MVP iteration and backtesting datasets
- use Redis for caching and queue support
- begin with cron-based polling if sufficient, and introduce Celery when queue
  orchestration becomes necessary
- preserve the agent-runtime baseline in
  `docs/specs/technical/agent-runtime/`

## 6. Example: Flight Collector (Python Pseudocode)

```python
import requests


def fetch_opensky_states():
    url = "https://opensky-network.org/api/states/all"
    data = requests.get(url).json()
    return data["states"]


def detect_military_activity(states):
    return [state for state in states if is_military(state)]


while True:
    states = fetch_opensky_states()
    military_flights = detect_military_activity(states)
    store(military_flights)
    sleep(60)
```

## 7. Example: Risk Scoring Function

```python
def compute_risk(features):
    score = (
        features["flight_anomaly"] * 0.4
        + features["notam_spike"] * 0.2
        + features["news_volume"] * 0.3
        + features["osint_activity"] * 0.1
        + features["pizza_index"] * 0.1
    )
    return score
```

## 8. Development Milestones

1. MVP ingestion pipeline
2. Signal extraction modules
3. Risk scoring model
4. Polymarket integration
5. Alerting system
6. Dashboard and analytics

Suggested milestone outcomes:

- **Milestone 1:** collector interfaces, scheduling, and raw observation
  persistence
- **Milestone 2:** normalized feature schema and first anomaly scoring pass
- **Milestone 3:** configurable weighted scoring with explainable breakdowns
- **Milestone 4:** market retrieval, market mapping, and divergence detection
- **Milestone 5:** notifications, alert history, and analyst review loop
- **Milestone 6:** operator dashboard with timelines and score-versus-market
  views

## 9. Best Practices

- cache API responses to avoid rate limits
- store historical data for backtesting
- log all signals with timestamps
- use modular collectors so new data sources can be added easily

## 10. MVP Boundaries

### In scope

- modular collectors for a small number of approved sources
- normalized feature snapshots with timestamps and source metadata
- a transparent weighted scoring model
- market comparison against selected geopolitical prediction markets
- alert generation, audit logging, and analyst-facing review

### Out of scope for the first implementation pass

- autonomous trade execution
- broad internet-scale scraping without source-by-source approval
- advanced satellite computer-vision pipelines
- opaque machine-learned forecasting models that cannot be easily explained

## 11. Immediate Planning Decisions

The next planning pass should confirm:

1. which source integrations are approved for phase one
2. the first geographic or conflict focus areas
3. market-selection rules for monitored prediction markets
4. thresholds for alert generation and analyst escalation
5. whether cron is sufficient initially or Celery is required from day one

## 12. Recommended Implementation Sequence

1. define backend domain models and collector contracts
2. draft the first API surface in `docs/api/openapi.yml`
3. scaffold ingestion and feature-processing services
4. add market comparison and alert logic
5. add the first operator dashboard views
